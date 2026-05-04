import json
from core import summarizer

text = """
REPORT Case Reference: CDSCO-AE-1882 Date Typed: 2024-05-20
Case Summary Report - Emergency Dept - City General Hospital in Haryana.
The patient [PATIENT_A7F3], male, 46-60 years old, 
was brought into the ER on Tuesday night in a state of severe respiratory distress. 
The patient developed severe anaphylactic reaction 30 minutes after evening dose of Cardioprin 75mg. 
Presented cyanotic at ER. Epinephrine and intubation attempted. 
Cardiac arrest occurred at 9:15 PM. Declared dead at 9:40 PM.
"""

result = summarizer.summarize(text)
print(json.dumps(result, indent=2))
