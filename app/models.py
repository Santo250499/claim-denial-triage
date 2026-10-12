"""Pydantic models = input validation. Bad payloads are rejected with 422."""
from pydantic import BaseModel, Field


class Denial(BaseModel):
    claim_id: str = Field(..., examples=["CLM-1001"])
    patient_name: str            # PHI
    dob: str                     # PHI (YYYY-MM-DD)
    member_id: str               # PHI
    payer: str
    carc_codes: list[str] = Field(..., description="Claim Adjustment Reason Codes, e.g. ['16']")
    rarc_codes: list[str] = []   # Remittance Advice Remark Codes, e.g. ['M51']
    amount: float = Field(..., ge=0)
    service_date: str | None = None
