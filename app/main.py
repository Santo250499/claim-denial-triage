"""FastAPI app: the webhook entry point.

Flow: auth -> validate -> mask PHI -> classify -> draft appeal -> store -> audit.
"""
import json
import logging
import time
from collections import Counter
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import config, storage
from app.classifier import get_provider
from app.masking import detokenise, mask_record
from app.models import Denial


# Structured (JSON) logging: one JSON object per line, easy to ship to Splunk/ELK.
class JsonFormatter(logging.Formatter):
    def format(self, r):
        return json.dumps({"ts": self.formatTime(r), "level": r.levelname,
                           "logger": r.name, "msg": r.getMessage()})


_h = logging.StreamHandler()
_h.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_h], force=True)
log = logging.getLogger("triage")

app = FastAPI(title="Claim Denial Triage")
WEB_UI = Path(__file__).resolve().parent.parent / "web" / "index.html"

# CORS is off unless origins are listed, e.g. the GitHub Pages demo:
# TRIAGE_CORS_ORIGINS=https://santo250499.github.io
if config.cors_origins():
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])
METRICS = Counter()  # simple in-process counters
STARTED = time.time()


def require_api_key(x_api_key: str = Header(default="")) -> str:
    """Access control: returns the client id, or 401. The key itself is never logged."""
    client = config.api_keys().get(x_api_key)
    if not client:
        METRICS["auth_failures"] += 1
        storage.audit("anonymous", "auth_failed")
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return client


@app.get("/", include_in_schema=False)
def web_ui():
    """Public demo page. Holds no data; every API call it makes still needs a key."""
    return FileResponse(WEB_UI, media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok", "uptime_s": round(time.time() - STARTED, 1)}


@app.get("/metrics")
def metrics(client: str = Depends(require_api_key)):
    return dict(METRICS)


@app.post("/webhook/denial")
def receive_denial(denial: Denial, client: str = Depends(require_api_key)):
    METRICS["denials_received"] += 1
    storage.audit(client, "denial_received", denial.claim_id)

    # 1. Mask PHI BEFORE anything goes to the AI provider.
    masked, vault = mask_record(denial.model_dump())

    # 2. Classify + draft using masked data only.
    provider = get_provider()
    result = provider.classify(masked)
    letter_masked = provider.draft_appeal(masked, result["category"])
    METRICS[f"category_{result['category']}"] += 1

    # 3. Persist the masked letter; return the real letter only to the authorised caller.
    rid = storage.save_result(denial.claim_id, denial.payer, result, provider.name, letter_masked)
    storage.audit(client, "denial_triaged", str(rid), f"category={result['category']} provider={provider.name}")
    log.info(f"triaged claim={denial.claim_id} record={rid} category={result['category']} provider={provider.name}")

    return {"record_id": rid, "claim_id": denial.claim_id, **result, "provider": provider.name,
            "appeal_letter": detokenise(letter_masked, vault)}


@app.get("/results/{rid}")
def read_result(rid: int, client: str = Depends(require_api_key)):
    row = storage.get_result(rid)
    if not row:
        raise HTTPException(404, "not found")
    storage.audit(client, "result_viewed", str(rid))
    return row
