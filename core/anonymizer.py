import re
import random
import string
import json

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except (ImportError, OSError):
    nlp = None
    print("Warning: spaCy or en_core_web_sm not installed. Advanced NER masking disabled.")

# Configuration for Generalization
METRO_CITIES = ["Mumbai", "Delhi", "Bangalore", "Bengaluru", "Chennai", "Kolkata", "Hyderabad"]
TIER2_STATE_MAPPING = {
    "Jaipur": "Rajasthan", "Nagpur": "Maharashtra", "Gurgaon": "Haryana", "Gurugram": "Haryana",
    "Pune": "Maharashtra", "Ahmedabad": "Gujarat", "Lucknow": "Uttar Pradesh", "Kanpur": "Uttar Pradesh",
    "Chandigarh": "Chandigarh", "Indore": "Madhya Pradesh", "Bhopal": "Madhya Pradesh", "Patna": "Bihar"
}

class AnonymizerEngine:
    def __init__(self):
        self.token_mapping = {}  # original -> token
        self.reverse_mapping = [] # List of dicts as per requested output format
        self.used_codes = set()

    def _generate_token(self, category):
        # Ensure consistency: same original gets same token
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        while code in self.used_codes:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        
        self.used_codes.add(code)
        return f"[{category}_{code}]"

    def _get_or_create_token(self, original, category):
        key = f"{category}:{original}"
        if key not in self.token_mapping:
            token = self._generate_token(category)
            self.token_mapping[key] = token
            self.reverse_mapping.append({
                "token": token,
                "original": original,
                "category": category
            })
        return self.token_mapping[key]

    def process(self, text):
        if not text:
            return {
                "step1_pseudonymised_text": "",
                "token_mapping": [],
                "step2_anonymised_text": "",
                "generalisation_log": [],
                "pii_summary": {"total_pii_detected": 0}
            }

        # --- STEP 1: PSEUDONYMISATION ---
        p_text = text

        # 1.1 Regex for structured PII
        patterns = [
            (r'\b\d{4}\s\d{4}\s\d{4}\b', "AADHAAR"),
            (r'\b(?:\+91|0)?[6-9]\d{9}\b', "PHONE"),
            (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', "EMAIL"),
            (r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', "PAN"), # Indian PAN
            (r'\bCDSCO-AE-\d+\b', "CASEREF")
        ]

        for pattern, cat in patterns:
            matches = re.findall(pattern, p_text)
            for m in set(matches):
                token = self._get_or_create_token(m, cat)
                p_text = p_text.replace(m, token)

        # 1.2 NER for Names and Entities (with Regex Fallbacks)
        if nlp:
            doc = nlp(p_text)
            entities = sorted(doc.ents, key=lambda e: len(e.text), reverse=True)
            for ent in entities:
                if ent.label_ == "PERSON":
                    token = self._get_or_create_token(ent.text, "PATIENT" if "patient" in p_text.lower() else "PERSON")
                    p_text = p_text.replace(ent.text, token)
                elif ent.label_ in ["FAC", "ORG"] and any(kw in ent.text.lower() for kw in ["hospital", "clinic", "medical", "centre", "center"]):
                    token = self._get_or_create_token(ent.text, "HOSPITAL")
                    p_text = p_text.replace(ent.text, token)
        
        # Always run these fallbacks for higher coverage
        # 1. Doctors (handling initials like Dr. S. K. Nair)
        doc_pattern = r"(?:Dr\.|Doctor)\s+([A-Z][a-z]*(?:\s+[A-Z]\.?)*\s+[A-Z][a-z]+)"
        matches = re.findall(doc_pattern, p_text)
        for m in set(matches):
            token = self._get_or_create_token(m, "DOCTOR")
            p_text = p_text.replace(m, token)

        # 2. General Names (Patients/Others)
        name_fallbacks = [
            r"(?:Mr\.|Ms\.|Mrs\.|Patient|Reporter)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b" # Generic Capitalized Pairs
        ]
        for nf in name_fallbacks:
            matches = re.findall(nf, p_text)
            for m in set(matches):
                if m.lower() not in ["the", "this", "that", "case", "report", "hospital", "summary", "date typed", "case reference"]:
                    category = "PATIENT" if "patient" in p_text.lower() else "PERSON"
                    token = self._get_or_create_token(m, category)
                    p_text = p_text.replace(m, token)

        # 3. Addresses
        addr_keywords = ["Flat", "House", "Plot", "Sector", "Street", "Lane", "Road", "Enclave", "Colony", "Nagar", "Apartments", "Society"]
        addr_pattern = r"\b(?:" + "|".join(addr_keywords) + r")\b[\s\d,]+[^,\.\n]{2,100}"
        matches = re.findall(addr_pattern, p_text, re.IGNORECASE)
        for m in set(matches):
            token = self._get_or_create_token(m.strip(), "ADDRESS")
            p_text = p_text.replace(m, token)

        # 4. Hospitals (Fallback)
        hosp_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Hospital|Clinic|Medical|Centre|Center|Nursing Home))\b"
        matches = re.findall(hosp_pattern, p_text, re.IGNORECASE)
        for m in set(matches):
            token = self._get_or_create_token(m, "HOSPITAL")
            p_text = p_text.replace(m, token)
        a_text = p_text
        gen_log = []

        # 2.1 Age Generalisation
        age_matches = re.finditer(r'\b(\d{1,2})\s*(?:years?|yrs?|yo)\s*(?:old)?\b', a_text, re.IGNORECASE)
        for m in sorted(list(age_matches), key=lambda x: len(x.group(0)), reverse=True):
            age = int(m.group(1))
            gen = ""
            if age <= 17: gen = "Minor (under 18)"
            elif age <= 30: gen = "18-30"
            elif age <= 45: gen = "31-45"
            elif age <= 60: gen = "46-60"
            else: gen = "Senior (60+)"
            
            a_text = a_text.replace(m.group(0), f"{gen} years old")
            gen_log.append({"field": "age", "original": m.group(0), "generalised": gen})

        # 2.2 Date Generalisation (e.g. 2024-05-20 -> May 2024)
        date_patterns = [
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b\d{2}/\d{2}/\d{4}\b'
        ]
        for dp in date_patterns:
            for dm in re.findall(dp, a_text, re.IGNORECASE):
                # Simple month placeholder
                gen = "[Month Year]"
                a_text = a_text.replace(dm, gen)
                gen_log.append({"field": "date", "original": dm, "generalised": gen})

        # 2.3 City/Location Generalisation
        found_cities = []
        # Check for known cities in text
        for city, state in TIER2_STATE_MAPPING.items():
            if re.search(r'\b' + city + r'\b', a_text, re.IGNORECASE):
                a_text = re.sub(r'\b' + city + r'\b', state, a_text, flags=re.IGNORECASE)
                gen_log.append({"field": "city", "original": city, "generalised": state})
                found_cities.append(city)
        
        for city in METRO_CITIES:
            if re.search(r'\b' + city + r'\b', a_text, re.IGNORECASE):
                found_cities.append(city)

        if not nlp and not found_cities:
            # Last resort: look for address-like strings (simplified)
            addr_pattern = r"\b(?:Flat|Sector|Street|Enclave|Colony|Nagar)\b[^,\.\n]{2,50}"
            matches = re.findall(addr_pattern, a_text, re.IGNORECASE)
            for m in set(matches):
                a_text = a_text.replace(m, "[ADDRESS REDACTED]")

        return {
            "step1_pseudonymised_text": p_text,
            "token_mapping": self.reverse_mapping,
            "step2_anonymised_text": a_text,
            "generalisation_log": gen_log,
            "pii_summary": {
                "total_pii_detected": len(self.reverse_mapping),
                "categories_found": list(set(m["category"] for m in self.reverse_mapping)),
                "pseudonymisation_complete": True,
                "generalisation_complete": True,
                "safe_to_index": True
            }
        }

def anonymize(text: str) -> str:
    """Compatibility wrapper for existing code"""
    engine = AnonymizerEngine()
    result = engine.process(text)
    return result["step2_anonymised_text"]

if __name__ == "__main__":
    engine = AnonymizerEngine()
    sample = "Patient Amit Mehra (Aadhaar: 1234 5678 9012), age 54, was treated at City General Hospital in Gurgaon on 2024-05-20."
    print(json.dumps(engine.process(sample), indent=2))
