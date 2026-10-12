"""SQLite storage + append-only audit log.

- `results` table stores the outcome. We store the claim id, category and
  the letter; PHI in the stored letter stays TOKENISED (minimum necessary).
- `audit` table has triggers that block UPDATE/DELETE => append-only.
  Each audit entry is also mirrored to a JSON-lines file.
"""
import json
import sqlite3
from datetime import datetime, timezone

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL, payer TEXT, category TEXT, action TEXT,
  confidence REAL, provider TEXT, appeal_letter_masked TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  record_id TEXT, detail TEXT);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def now():
    return datetime.now(timezone.utc).isoformat()


def audit(actor: str, action: str, record_id: str | None = None, detail: str = ""):
    """Record who/when/what/which record. Callers must never pass raw PHI here."""
    entry = {"ts": now(), "actor": actor, "action": action, "record_id": record_id, "detail": detail}
    with connect() as conn:
        conn.execute("INSERT INTO audit (ts, actor, action, record_id, detail) VALUES (?,?,?,?,?)",
                     tuple(entry.values()))
    with open(config.AUDIT_LOG_PATH, "a") as f:  # "a" = append mode only
        f.write(json.dumps(entry) + "\n")


def save_result(claim_id, payer, result, provider, letter_masked) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO results (claim_id,payer,category,action,confidence,provider,"
            "appeal_letter_masked,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (claim_id, payer, result["category"], result["action"],
             result.get("confidence"), provider, letter_masked, now()))
        return cur.lastrowid


def get_result(rid: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM results WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None
