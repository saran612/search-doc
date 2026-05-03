import os
import re
import json
import requests

# ─── Optional LLM Config (shared with summarizer.py) ────────────────────────
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL   = os.getenv("LLM_MODEL",   "llama3-8b-8192")

VALID_CATEGORIES = ["Death", "Disability", "Hospitalisation", "Other"]


def _llm_classify(summary: dict) -> dict:
    """Use LLM to classify based on the structured summary."""
    prompt = f"""You are a regulatory case classifier for CDSCO adverse event reports.

Classification rules (strict priority order):
- "Death"           → patient died as a result of the event
- "Disability"      → permanent or significant functional impairment
- "Hospitalisation" → required inpatient admission or prolonged stay
- "Other"           → any adverse event not meeting the above criteria

Pick EXACTLY ONE category. Apply the HIGHEST priority that fits.

Return ONLY valid JSON:
{{
  "category": "<Death | Disability | Hospitalisation | Other>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<1-2 sentence factual justification citing evidence from the summary>"
}}

Case Summary:
{json.dumps(summary, indent=2)}
"""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    result = json.loads(raw)

    # Guardrail: reject hallucinated categories
    if result.get("category") not in VALID_CATEGORIES:
        result["category"] = "Other"
        result["confidence"] = 0.0
        result["reasoning"] = "Classification failed — defaulted to Other."

    return result


def _rule_based_classify(summary: dict) -> dict:
    """
    Deterministic keyword classifier.
    Reads from the structured summary dict produced by summarizer.py.
    Priority: Death > Disability > Hospitalisation > Other
    """
    outcome    = (summary.get("outcome") or "").lower()
    severity   = (summary.get("severity") or "").lower()
    event_desc = (summary.get("event_description") or "").lower()
    findings   = (summary.get("key_findings") or "").lower()
    all_text   = f"{outcome} {severity} {event_desc} {findings}"

    # Death
    death_keywords = ["fatal", "death", "died", "deceased", "mortality"]
    if any(k in all_text for k in death_keywords) or outcome == "fatal":
        return {
            "category":   "Death",
            "confidence": 0.92,
            "reasoning":  "Keywords indicating fatality (fatal/death/died) detected in outcome or event description."
        }

    # Disability
    disability_keywords = [
        "disability", "disabled", "permanent", "paralys", "impair",
        "amputation", "blind", "deaf", "loss of function"
    ]
    if any(k in all_text for k in disability_keywords):
        return {
            "category":   "Disability",
            "confidence": 0.85,
            "reasoning":  "Keywords indicating permanent functional impairment detected."
        }

    # Hospitalisation
    hospital_keywords = [
        "hospitaliz", "hospitalis", "admitted", "inpatient",
        "icu", "intensive care", "emergency", "er visit", "prolonged stay"
    ]
    if any(k in all_text for k in hospital_keywords):
        return {
            "category":   "Hospitalisation",
            "confidence": 0.80,
            "reasoning":  "Keywords indicating inpatient admission or emergency care detected."
        }

    # Other
    return {
        "category":   "Other",
        "confidence": 0.65,
        "reasoning":  "No fatal, disability, or hospitalisation indicators found. Classified as Other."
    }


def classify(summary: dict) -> dict:
    """
    Main entry point.
    Expects the structured summary dict produced by summarizer.summarize().
    Uses LLM if configured; otherwise falls back to rule-based classifier.
    """
    if LLM_API_URL and LLM_API_KEY:
        try:
            return _llm_classify(summary)
        except Exception as e:
            print(f"[classifier] LLM call failed ({e}), falling back to rule-based.")

    return _rule_based_classify(summary)


if __name__ == "__main__":
    sample_summary = {
        "patient_info": "Male, 52 years",
        "drug_name": "Warfarin 5mg",
        "event_description": "Patient suffered a fatal haemorrhagic stroke",
        "severity": "Fatal",
        "outcome": "Fatal",
        "key_findings": "CT head: large intracerebral haemorrhage"
    }
    result = classify(sample_summary)
    print(json.dumps(result, indent=2))
