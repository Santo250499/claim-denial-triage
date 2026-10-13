# claim-denial-triage

A small, working demo of an **automated insurance claim-denial triage service** for US healthcare
revenue cycle management (RCM). A billing system or clearinghouse POSTs a denial (835-style CARC/RARC
codes) to a webhook; the service masks the PHI, classifies the denial, drafts an appeal letter with
an LLM (or a deterministic rule engine), stores the result and writes an audit trail.

> All data in this repo is **synthetic**. No real PHI is used.

## Try it live

**[santo250499.github.io/claim-denial-triage](https://santo250499.github.io/claim-denial-triage/)**

Pick a sample denial (or type your own) and press *Triage this denial*. The page walks the record through
every step and shows it exactly as each part of the system sees it: the raw payload, the masked record
the AI provider receives, the tokenised row in the database, the real letter returned to the caller,
and the audit trail. A built-in check confirms no name, DOB or member ID crossed the trust boundary.

- **In-browser mode** (default) runs a JavaScript port of the masking, CARC rule engine and letter
  template. Nothing leaves your browser, and the HMAC tokens are byte-for-byte identical to the
  Python service's (same algorithm, demo secret).
- **Live API mode** sends the denial to a running copy of this FastAPI service. The same page is served
  at `/` by the app itself, so `uvicorn app.main:app` then <http://127.0.0.1:8000> works locally too.
  To call a hosted server from the GitHub Pages site, open
  `https://santo250499.github.io/claim-denial-triage/?api=https://YOUR-SERVER` and enter its API key.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Santo250499/claim-denial-triage)
— hosts the real API + UI using `render.yaml` (set `TRIAGE_API_KEYS` when prompted).

## Architecture

```mermaid
flowchart LR
    A[Billing system / clearinghouse] -->|POST /webhook/denial + X-API-Key| B[FastAPI]
    B --> C{API key valid?}
    C -- no --> X[401 + audit auth_failed]
    C -- yes --> D[Pydantic validation]
    D --> E[PHI masking / HMAC tokens]
    E -->|masked data only| F{Provider}
    F -->|LLM_API_KEY set| G[OpenAI-compatible LLM]
    F -->|no key / LLM error| H[Rule-based CARC engine]
    G --> I[Category + appeal draft with tokens]
    H --> I
    I --> J[(SQLite results - tokenised)]
    I --> K[(Append-only audit table + audit.log)]
    I -->|detokenise locally| L[Response to authorised caller]
```

| File | Purpose |
|---|---|
| `app/main.py` | Endpoints, API-key auth, JSON logging, metrics |
| `app/masking.py` | PHI tokenisation (HMAC), regex scrubbing, detokenise |
| `app/classifier.py` | Provider pattern: `RuleBasedProvider` and `OpenAICompatibleProvider` |
| `app/storage.py` | SQLite results + append-only audit (triggers block UPDATE/DELETE) |
| `app/config.py` | All settings from env vars |
| `web/index.html` | Live demo UI (GitHub Pages + served at `/` by the app) |
| `.github/workflows/` | Tests on every push; Pages deploy of `web/` |

Endpoints: `GET /` (demo UI, public), `GET /health` (public), `POST /webhook/denial`, `GET /results/{id}`, `GET /metrics` (all need `X-API-Key`).

## HIPAA-minded design choices
- **Minimum necessary:** the LLM gets only the fields it needs, with PHI swapped for tokens. The DB keeps
  only the *tokenised* letter. The real letter goes back only to the authenticated caller.
- **Masking / tokenisation:** name, DOB and member ID become `[PATIENT_ab12cd34]`-style HMAC tokens
  (same value gives the same token, and you can't reverse one without `TOKEN_SECRET`). Free text is also regex-scrubbed for dates/SSNs.
- **Access control:** every endpoint except `/health` needs an API key. Keys map to a client id, so we know *who*
  acted and the key itself is never logged or stored.
- **Auditability:** each receive/triage/view/auth-failure is logged with who, when, action and record id, and no PHI.
  SQLite triggers make the audit table append-only, and the file log is opened in append mode.
- **Secure AI use:** the provider is pluggable through env vars (`LLM_BASE_URL` can point at a BAA-covered or
  self-hosted endpoint), temperature is 0, and any LLM failure falls back to the deterministic rules so the pipeline never
  breaks. A test proves the LLM prompt never contains raw PHI.
- **Ops:** JSON logs (ready for SIEM), a non-root Docker user, and secrets only from the environment.
  *For production you'd add:* TLS, a secrets manager, encryption at rest, key rotation, and a human review before any appeal is sent.

## Run it
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -v                                   # 15 tests
uvicorn app.main:app --port 8000            # rules mode; UI at http://127.0.0.1:8000
python scripts/send_sample.py               # in another terminal
# Optional LLM mode:
export LLM_API_KEY=sk-... LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o-mini
# Docker:
docker build -t denial-triage . && docker run -p 8000:8000 -e TRIAGE_API_KEYS=dev-key-123:demo-client denial-triage
```
Env vars: `TRIAGE_API_KEYS` (`key:client,...`), `TOKEN_SECRET`, `TRIAGE_DB_PATH`, `TRIAGE_AUDIT_LOG`,
`TRIAGE_CORS_ORIGINS` (comma-separated browser origins allowed to call the API; empty = CORS off), `LLM_*`.

See `docs/demo-output.txt` and `docs/test-output.txt` for a recorded run.
