import re

def check_missing_fields(text):
    """
    Checks the provided text for required fields and returns a list of missing ones.
    Uses case-insensitive regex to find field labels followed by a colon or space.
    """
    required_fields = {
        "Name": r"\b(name|patient|full\s*name)\b\s*[:\-]?\s*([A-Z]|\[PATIENT_NAME\])",
        "DoB": r"\b(dob|date\s*of\s*birth|birth\s*date)\b\s*[:\-]?\s*(\d|\[DATE REDACTED\])",
        "Address": r"\b(address|location|residence)\b\s*[:\-]?\s*(\w|\[LOCATION REDACTED\])",
        "Email": r"\b(email|e-mail|mail\s*id)\b\s*[:\-]?\s*(\w|\[EMAIL REDACTED\])",
        "Phone": r"\b(phone|mobile|contact|tel|telephone)\b\s*[:\-]?\s*(\d|\+|\[PHONE REDACTED\])"
    }
    
    missing_fields = []
    
    for field, pattern in required_fields.items():
        if not re.search(pattern, text, re.IGNORECASE):
            missing_fields.append(field)
            
    return missing_fields

