"""
validator.py — pure deterministic logic, no LLM calls.
Fast, cheap, and fully auditable — critical for regulatory systems.
"""

REQUIRED_FIELDS = ["patient_info", "drug_name", "event_description", "outcome"]

VALID_SEVERITIES = {"Mild", "Moderate", "Severe", "Life-threatening", "Fatal", None}
VALID_OUTCOMES   = {"Recovered", "Recovering", "Not Recovered", "Fatal", "Unknown", None}
VALID_CATEGORIES = {"Death", "Disability", "Hospitalisation", "Other"}


def validate(summary: dict, classification: dict | None = None) -> dict:
    """
    Validates a summary dict (from summarizer) and an optional classification
    dict (from classifier).

    Returns:
    {
        "is_valid": bool,          # False if ANY hard errors exist
        "errors":   [...],         # Hard failures — block or escalate
        "warnings": [...]          # Soft flags — notify reviewer
    }

    Error shape:  { "field": str, "issue": str, "value": any }
    Warning shape: { "issue": str, "detail": str }
    """
    errors   = []
    warnings = []

    # ── 1. Missing required fields ────────────────────────────────────────────
    for field in REQUIRED_FIELDS:
        if not summary.get(field):
            errors.append({
                "field": field,
                "issue": "MISSING_REQUIRED_FIELD",
                "value": None
            })

    # ── 2. Controlled vocabulary checks ──────────────────────────────────────
    severity = summary.get("severity")
    if severity not in VALID_SEVERITIES:
        errors.append({
            "field": "severity",
            "issue": "INVALID_VALUE",
            "value": severity
        })

    outcome = summary.get("outcome")
    if outcome not in VALID_OUTCOMES:
        errors.append({
            "field": "outcome",
            "issue": "INVALID_VALUE",
            "value": outcome
        })

    # ── 3. Logical consistency checks ────────────────────────────────────────
    if severity == "Fatal" and outcome != "Fatal":
        warnings.append({
            "issue":  "INCONSISTENCY",
            "detail": "severity is 'Fatal' but outcome is not 'Fatal'"
        })

    if outcome == "Fatal" and severity not in ("Fatal", "Life-threatening", None):
        warnings.append({
            "issue":  "INCONSISTENCY",
            "detail": f"outcome is 'Fatal' but severity is '{severity}' — consider updating severity"
        })

    if classification:
        category = classification.get("category")

        if category not in VALID_CATEGORIES:
            errors.append({
                "field": "category",
                "issue": "INVALID_CATEGORY",
                "value": category
            })

        if category == "Death" and outcome != "Fatal":
            warnings.append({
                "issue":  "INCONSISTENCY",
                "detail": "Classified as 'Death' but outcome field is not 'Fatal'"
            })

        if outcome == "Fatal" and category != "Death":
            warnings.append({
                "issue":  "INCONSISTENCY",
                "detail": f"outcome is 'Fatal' but classified as '{category}' — consider reclassifying as 'Death'"
            })

        # ── 4. Low-confidence flag ────────────────────────────────────────────
        confidence = classification.get("confidence", 1.0)
        if isinstance(confidence, (int, float)) and confidence < 0.6:
            warnings.append({
                "issue":  "LOW_CONFIDENCE",
                "detail": f"Classification confidence is {confidence:.2f} — queue for manual review"
            })

    return {
        "is_valid": len(errors) == 0,
        "errors":   errors,
        "warnings": warnings
    }


if __name__ == "__main__":
    import json

    # Test: all good
    summary_ok = {
        "patient_info":      "Male, 52",
        "drug_name":         "Warfarin 5mg",
        "event_description": "Haemorrhagic stroke",
        "severity":          "Fatal",
        "outcome":           "Fatal",
        "key_findings":      "CT: large ICH"
    }
    classification_ok = {"category": "Death", "confidence": 0.92, "reasoning": "..."}
    print("=== Valid case ===")
    print(json.dumps(validate(summary_ok, classification_ok), indent=2))

    # Test: errors + warnings
    summary_bad = {
        "patient_info":      None,        # MISSING
        "drug_name":         "Aspirin",
        "event_description": "Rash",
        "severity":          "CRITICAL",  # INVALID
        "outcome":           "Fatal",
        "key_findings":      None
    }
    classification_bad = {"category": "Other", "confidence": 0.4, "reasoning": "..."}
    print("\n=== Invalid case ===")
    print(json.dumps(validate(summary_bad, classification_bad), indent=2))
