"""Send synthetic (fake) denials to a running server. Usage: python scripts/send_sample.py"""
import json, os
import httpx

URL = os.getenv("TRIAGE_URL", "http://127.0.0.1:8000")
KEY = os.getenv("TRIAGE_KEY", "dev-key-123")

SAMPLES = [
    {"claim_id": "CLM-1001", "patient_name": "Alex Fakeperson", "dob": "1975-04-12", "member_id": "MBR000111",
     "payer": "Acme Mock Insurance", "carc_codes": ["197"], "rarc_codes": ["N54"], "amount": 1250.00},
    {"claim_id": "CLM-1002", "patient_name": "Sam Notreal", "dob": "1990-09-30", "member_id": "MBR000222",
     "payer": "Example Health", "carc_codes": ["16"], "rarc_codes": ["M51"], "amount": 310.50},
    {"claim_id": "CLM-1003", "patient_name": "Pat Synthetic", "dob": "1962-12-01", "member_id": "MBR000333",
     "payer": "Demo Care", "carc_codes": ["29"], "rarc_codes": [], "amount": 88.00},
]

for s in SAMPLES:
    r = httpx.post(f"{URL}/webhook/denial", json=s, headers={"X-API-Key": KEY})
    print(r.status_code, json.dumps(r.json(), indent=2))
print("bad key ->", httpx.post(f"{URL}/webhook/denial", json=SAMPLES[0], headers={"X-API-Key": "wrong"}).status_code)
print("metrics ->", httpx.get(f"{URL}/metrics", headers={"X-API-Key": KEY}).json())
