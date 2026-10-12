import os
import pytest


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    """Each test gets a fresh DB and audit log, and no LLM key (rules provider)."""
    from app import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "RAW_KEYS", "test-key:tester")
    yield


SAMPLE = {"claim_id": "CLM-T1", "patient_name": "Jane Testcase", "dob": "1980-01-31",
          "member_id": "XYZ998877", "payer": "Mock Health Plan",
          "carc_codes": ["50"], "rarc_codes": ["N115"], "amount": 420.0}
