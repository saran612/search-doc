import os
import re
import json
import requests

# ─── Optional LLM Config (set LLM_API_URL + LLM_API_KEY in .env) ────────────
# Works with any OpenAI-compatible endpoint (OpenAI, Groq, Ollama, etc.)
LLM_API_URL = os.getenv("LLM_API_URL", "")          # e.g. https://api.groq.com/openai/v1/chat/completions
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL   = os.getenv("LLM_MODEL",   "llama3-8b-8192")

SUMMARY_FIELDS = [
    "patient_info", "drug_name", "event_description",
    "severity", "outcome", "key_findings"
]


def _llm_summarize(text: str) -> dict:
    """Call an OpenAI-compatible LLM to extract summary fields."""
    prompt = f"""You are a regulatory document summarizer for CDSCO adverse event reports.

Extract ONLY what is explicitly stated. If a field is absent, use null — do NOT infer or hallucinate.

Return ONLY valid JSON in this exact shape:
{{
  "patient_info": "<age/sex/weight if present, else null>",
  "drug_name": "<suspect drug name + dose if mentioned>",
  "event_description": "<concise clinical description of the adverse event>",
  "severity": "<Mild | Moderate | Severe | Life-threatening | Fatal>",
  "outcome": "<Recovered | Recovering | Not Recovered | Fatal | Unknown>",
  "key_findings": "<lab values, diagnoses, or clinical notes relevant to regulatory review>"
}}

Document:
\"\"\"
{text[:6000]}
\"\"\"
"""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }
    response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]

    # Strip markdown fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    return json.loads(raw)


def _rule_based_summarize(text: str) -> dict:
    """Fast deterministic fallback when no LLM is configured."""

    def find(patterns, flags=re.IGNORECASE):
        for p in patterns:
            m = re.search(p, text, flags)
            if m:
                try:
                    return m.group(1).strip()
                except IndexError:
                    return m.group(0).strip()
        return None

    # Patient info
    patient_info = find([
        r"(?:patient|name)\s*[:\-]\s*([^\n,;\.]+)",
        r"(?:age|sex|gender|weight)\s*[:\-]\s*([^\n,;\.]+)",
        r"(?:The\s+)?patient\s+([^,]+,\s*(?:male|female|m|f),\s*\d+\s*years?\s*old)",
        r"(?:patient)\s+([A-Za-z\s\[\]_]+)\b"
    ])

    # Drug name
    drug_name = None
    drug_name_match = re.search(r"(?:drug|medicine|medication|suspect\s*drug)\s*[:\-]\s*([^\n,;\.]+)", text, re.IGNORECASE)
    if drug_name_match:
        drug_name = drug_name_match.group(1).strip()
    else:
        # Fallback for natural language like "prescribed Cardioprin 75mg" or "taking Amoxicillin"
        verb_match = re.search(r"(?:prescribed|taking|started\s*on|given)\s+([A-Z][a-zA-Z0-9\-]+(?:\s+\d+(?:mg|g|ml|mcg))?)", text, re.IGNORECASE)
        if verb_match:
            drug_name = verb_match.group(1).strip()
        else:
            # Fallback for "tablet of X" or "injection X"
            form_match = re.search(r"(?:tablet|capsule|injection|syrup)\s+(?:of\s+)?([A-Za-z0-9]+)", text, re.IGNORECASE)
            if form_match and form_match.group(1).lower() not in ["of", "for", "the", "a", "in", "and", "is"]:
                drug_name = form_match.group(1).strip()

    # Severity
    severity_match = re.search(
        r"\b(mild|moderate|severe|life[-\s]threatening|fatal)\b", text, re.IGNORECASE
    )
    severity = severity_match.group(1).capitalize() if severity_match else None

    # Outcome
    outcome_match = re.search(
        r"\b(recovered|recovering|not\s+recovered|fatal|unknown)\b", text, re.IGNORECASE
    )
    outcome = outcome_match.group(1).capitalize() if outcome_match else None

    # Event description – grab first 2 sentences with "adverse" or "event" or "reaction"
    event_match = re.search(
        r"(?:adverse\s+event|adverse\s+reaction|side\s+effect|complaint)[:\-]?\s*(.{20,300})",
        text, re.IGNORECASE
    )
    event_description = event_match.group(1).strip() if event_match else None

    # Key findings – lab values, diagnoses, clinical states
    key_findings = find([
        r"(?:lab(?:oratory)?\s*(?:result|value|finding|tests?)|diagnosis|diagnose[sd]|key\s*findings?)[:\-]?\s*([^\n\.]+)",
        r"(?:state\s*of|presented\s*with|signs\s*of|symptoms\s*of|diagnosed\s*with|history\s*of|secondary\s*to)\s+([a-zA-Z\s\-]+?)(?:\.|,|and|with|\n)",
        r"(?:blood\s*pressure|BP|heart\s*rate|HR|SpO2|oxygen|ECG|temperature)\s*(?:was|is|showed|measured|at)?\s*([^\n\.,;]+)"
    ])

    return {
        "patient_info":      patient_info,
        "drug_name":         drug_name,
        "event_description": event_description,
        "severity":          severity,
        "outcome":           outcome,
        "key_findings":      key_findings
    }


def summarize(text: str) -> dict:
    """
    Main entry point.
    Uses LLM if LLM_API_URL and LLM_API_KEY are set; otherwise falls back to
    rule-based extraction.
    """
    if LLM_API_URL and LLM_API_KEY:
        try:
            return _llm_summarize(text)
        except Exception as e:
            print(f"[summarizer] LLM call failed ({e}), falling back to rule-based.")

    return _rule_based_summarize(text)


if __name__ == "__main__":
    sample = """
    Patient: John Doe, Male, 45 years, 70kg.
    Suspect Drug: Amoxicillin 500mg TDS.
    Adverse Event: Patient developed severe skin rash and difficulty breathing
    within 30 minutes of taking the drug. Severity: Severe.
    Outcome: Recovered after treatment.
    Lab Findings: WBC elevated at 12,000.
    """
    result = summarize(sample)
    print(json.dumps(result, indent=2))
