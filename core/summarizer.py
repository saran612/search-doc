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

    # 1. Helper to strip noise/headers for cleaner narrative extraction
    clean_text = re.sub(r'(?:REPORT|Case Reference|Date Typed|Case Summary Report|Page \d+).*?\n', '', text, flags=re.IGNORECASE)
    
    def find_all(patterns, flags=re.IGNORECASE):
        found = []
        for p in patterns:
            matches = re.finditer(p, text, flags)
            for m in matches:
                try:
                    val = m.group(1).strip()
                except IndexError:
                    val = m.group(0).strip()
                if val and val not in found:
                    found.append(val)
        return found

    def find_first(patterns, flags=re.IGNORECASE):
        for p in patterns:
            m = re.search(p, text, flags)
            if m:
                try:
                    return m.group(1).strip()
                except IndexError:
                    return m.group(0).strip()
        return None

    # Patient info (extract generalized age and token)
    p_info_parts = find_all([
        r"(\[PATIENT_[A-Z0-9]{4}\])",
        r"\b(\d{2}-\d{2})\s+years?\b", # Require "years" after range if it's XX-XX
        r"\b(\d{1,2}\+|\bSenior\b|\bMinor\b)(?:\s+years?\s*(?:old)?)?\b",
        r"\b(male|female|other)\b"
    ])
    # Filter out potential date fragments like 24-05 from 2024-05-20
    patient_info = ", ".join([p for p in p_info_parts if not re.match(r'^\d{2}-\d{2}$', p) or any(kw in text.lower() for kw in ["age", "years", "old"])])
    if not patient_info and p_info_parts:
        patient_info = ", ".join(p_info_parts)

    # Drug name
    drug_name = find_first([
        r"(?:drug|medicine|medication|suspect\s*drug)\s*[:\-]\s*([^\n,;\.]+)",
        r"(?:prescribed|taking|started\s*on|given|dose\s*of)\s+([A-Z][a-zA-Z0-9\-]+(?:\s+\d+(?:mg|g|ml|mcg))?)",
        r"(?:tablet|capsule|injection|syrup)\s+(?:of\s+)?([A-Za-z0-9]+)"
    ])
    if drug_name and drug_name.lower() in ["of", "for", "the", "a", "in", "and", "is"]:
        drug_name = None

    # Severity & Outcome
    severity = find_first([r"\b(mild|moderate|severe|life[-\s]threatening|fatal|dead|death|died)\b"])
    if severity: 
        if severity.lower() in ["dead", "death", "died"]: severity = "Fatal"
        else: severity = severity.capitalize()
    
    outcome = find_first([r"\b(recovered|recovering|not\s+recovered|fatal|dead|death|died|unknown)\b"])
    if outcome:
        if outcome.lower() in ["dead", "death", "died"]: outcome = "Fatal"
        else: outcome = outcome.capitalize()

    # Event Description - Look for the clinical narrative
    narrative = None
    # More flexible sentence matching
    narrative_matches = re.finditer(r"([^.!?]{20,}[^.!?]+(?:developed|presented|admitted|reported|observed|found|started|suffered|declared|brought|occurred)[^.!?]+[.!?])", clean_text, re.IGNORECASE | re.DOTALL)
    narrative_sentences = [m.group(1).strip().replace('\n', ' ') for m in narrative_matches]
    if narrative_sentences:
        narrative = " ".join(narrative_sentences[:3]) 
    else:
        # Fallback to keywords
        event_match = re.search(r"(?:adverse\s+event|adverse\s+reaction|side\s+effect|event\s+description|summary)[:\-]?\s*(.{20,400})", clean_text, re.IGNORECASE | re.DOTALL)
        if event_match:
            narrative = event_match.group(1).strip().replace('\n', ' ')

    # Key Findings - Collect ALL matching findings
    findings_list = find_all([
        r"(?:lab(?:oratory)?|diagnosis|diagnose[sd]|key\s*findings?|findings?)[:\-]?\s*([^\n\.]+)",
        r"(?:state\s*of|presented\s*with|signs\s*of|symptoms\s*of|diagnosed\s*with|history\s*of|secondary\s*to)\s+([a-zA-Z\s\-]{3,50})(?:\.|,|and|with|\n)",
        r"\b(cyanosis|cyanotic|anaphylaxis|anaphylactic|arrest|hypotension|hypertension|respiratory\s*distress|tachycardia|bradycardia|seizure|rash|unconscious|unresponsive)\b",
        r"(?:blood\s*pressure|BP|heart\s*rate|HR|SpO2|oxygen|ECG|temperature)\s*(?:was|is|showed|measured|at)?\s*([^\n\.,;]+)"
    ])
    key_findings = ", ".join(findings_list) if findings_list else None

    return {
        "patient_info":      patient_info,
        "drug_name":         drug_name,
        "event_description": narrative,
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
