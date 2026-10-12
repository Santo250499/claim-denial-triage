"""PHI masking / tokenisation.

Before ANY data leaves our trust boundary (e.g. to an LLM), PHI fields are
replaced with opaque tokens like [PATIENT_1a2b3c]. The token is a keyed hash
(HMAC) so the same patient always gets the same token, but it can't be
reversed without the secret. The real values are re-inserted locally only
when the final letter is produced ("detokenise").
"""
import hashlib
import hmac
import os
import re

SECRET = os.getenv("TOKEN_SECRET", "local-dev-secret").encode()
PHI_FIELDS = {"patient_name": "PATIENT", "dob": "DOB", "member_id": "MEMBER"}


def token_for(label: str, value: str) -> str:
    digest = hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()[:8]
    return f"[{label}_{digest}]"


def mask_record(record: dict) -> tuple[dict, dict]:
    """Return (masked_copy, vault). vault maps token -> real value, kept in memory only."""
    masked, vault = dict(record), {}
    for field, label in PHI_FIELDS.items():
        if masked.get(field):
            tok = token_for(label, str(masked[field]))
            vault[tok] = str(masked[field])
            masked[field] = tok
    return masked, vault


# Defence in depth: scrub anything that still *looks* like PHI in free text.
_PATTERNS = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[DATE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
]


def scrub_text(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def detokenise(text: str, vault: dict) -> str:
    for tok, real in vault.items():
        text = text.replace(tok, real)
    return text
