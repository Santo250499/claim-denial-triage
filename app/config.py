"""Central configuration, read from environment variables (12-factor style).

Secrets (API keys) are NEVER hard-coded; they come from the environment.
"""
import os

# Comma-separated list of API keys allowed to call the webhook.
# Each key maps to a "client id" so the audit log can record *who* acted
# without storing the secret itself. Format: "key1:billing-system,key2:qa-user"
RAW_KEYS = os.getenv("TRIAGE_API_KEYS", "dev-key-123:demo-client")

DB_PATH = os.getenv("TRIAGE_DB_PATH", "triage.db")
AUDIT_LOG_PATH = os.getenv("TRIAGE_AUDIT_LOG", "audit.log")

# LLM settings. If LLM_API_KEY is empty, the rule-based fallback is used.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Browser origins allowed to call the API (comma-separated). Empty = no CORS.
CORS_ORIGINS = os.getenv("TRIAGE_CORS_ORIGINS", "")


def cors_origins() -> list[str]:
    return [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]


def api_keys() -> dict[str, str]:
    """Parse TRIAGE_API_KEYS into {key: client_id}."""
    keys = {}
    for pair in RAW_KEYS.split(","):
        if ":" in pair:
            k, client = pair.split(":", 1)
            keys[k.strip()] = client.strip()
    return keys
