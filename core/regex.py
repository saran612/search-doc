import re

def check_missing_fields(text):
    """
    Checks the provided text for required fields and returns a list of missing ones.
    Uses case-insensitive regex to find field labels followed by a colon or space.
    """
    required_fields = {
        "Name": r"name\s*[:\-]",
        "DoB": r"(dob|date\s*of\s*birth)\s*[:\-]",
        "Address": r"address\s*[:\-]",
        "Email": r"(email|e-mail)\s*[:\-]",
        "Phone": r"(phone|mobile|contact|tel)\s*[:\-]"
    }
    
    missing_fields = []
    
    for field, pattern in required_fields.items():
        if not re.search(pattern, text, re.IGNORECASE):
            missing_fields.append(field)
            
    return missing_fields

if __name__ == "__main__":
    # Test cases
    test_text = "Name: John Doe, Email: john@example.com"
    missing = check_missing_fields(test_text)
    print(f"Test 1 - Missing: {missing}")
    
    test_text_2 = "Full Name - Jane, Date of Birth: 1990-01-01, Address - 123 Lane"
    missing_2 = check_missing_fields(test_text_2)
    print(f"Test 2 - Missing: {missing_2}")
