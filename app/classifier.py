"""Denial classification + appeal drafting.

Provider pattern: `get_provider()` returns an LLM provider if LLM_API_KEY is
set, otherwise the deterministic RuleBasedProvider. Both expose the same
two methods, so the rest of the app doesn't care which one is used.
Only MASKED data is ever passed to a provider.
"""
import json
import logging

import httpx

from app import config

log = logging.getLogger("triage.classifier")

# Small lookup of common CARC codes -> (category, recommended action).
CARC_RULES = {
    "16": ("missing_information", "Correct/add missing claim data and resubmit"),
    "18": ("duplicate", "Verify original claim status; do not resubmit"),
    "27": ("eligibility", "Verify coverage dates with payer; bill correct payer"),
    "29": ("timely_filing", "Appeal with proof of timely filing (clearinghouse report)"),
    "50": ("medical_necessity", "Appeal with medical records / letter of medical necessity"),
    "96": ("non_covered", "Check benefits; obtain ABN or bill patient if allowed"),
    "97": ("bundling", "Review NCCI edits; add modifier if separately payable"),
    "197": ("authorization", "Appeal with prior-auth number or request retro-auth"),
    "4": ("coding", "Review procedure code/modifier and correct"),
}


class RuleBasedProvider:
    name = "rules"

    def classify(self, masked: dict) -> dict:
        for code in masked["carc_codes"]:
            # Strip group-code prefix: "CO-197" -> "197" (CO/PR/OA/PI = who owes)
            c = code.upper().split("-")[-1]
            if c in CARC_RULES:
                cat, action = CARC_RULES[c]
                return {"category": cat, "action": action, "confidence": 0.9}
        return {"category": "other", "action": "Route to human reviewer", "confidence": 0.3}

    def draft_appeal(self, masked: dict, category: str) -> str:
        return (
            f"To: {masked['payer']} Appeals Department\n"
            f"Re: Claim {masked['claim_id']} | Patient {masked['patient_name']} | "
            f"Member ID {masked['member_id']} | DOB {masked['dob']}\n\n"
            f"We request reconsideration of the denial (CARC {', '.join(masked['carc_codes'])}"
            f"{'; RARC ' + ', '.join(masked['rarc_codes']) if masked['rarc_codes'] else ''}) "
            f"for the amount of ${masked['amount']:.2f}. The denial was categorised as "
            f"'{category.replace('_', ' ')}'. Supporting documentation is enclosed.\n\n"
            "Sincerely,\nBilling Appeals Team"
        )


class OpenAICompatibleProvider:
    """Works with any OpenAI-compatible /chat/completions endpoint (OpenAI, Azure, local vLLM...)."""
    name = "llm"

    def __init__(self):
        self.fallback = RuleBasedProvider()

    def _chat(self, prompt: str) -> str:
        r = httpx.post(
            f"{config.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json={"model": config.LLM_MODEL, "temperature": 0,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def classify(self, masked: dict) -> dict:
        prompt = ("Classify this insurance claim denial. Reply ONLY with JSON keys "
                  "category, action, confidence (0-1).\n" + json.dumps(masked))
        try:
            return json.loads(self._chat(prompt))
        except Exception as e:  # network error, bad JSON... never crash the pipeline
            log.warning("LLM classify failed, using rules: %s", type(e).__name__)
            return self.fallback.classify(masked)

    def draft_appeal(self, masked: dict, category: str) -> str:
        prompt = ("Draft a concise, professional appeal letter. Keep placeholder tokens "
                  f"in square brackets exactly as-is. Category: {category}\n" + json.dumps(masked))
        try:
            return self._chat(prompt)
        except Exception as e:
            log.warning("LLM draft failed, using rules: %s", type(e).__name__)
            return self.fallback.draft_appeal(masked, category)


def get_provider():
    return OpenAICompatibleProvider() if config.LLM_API_KEY else RuleBasedProvider()
