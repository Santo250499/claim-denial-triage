import json

from fastapi.testclient import TestClient

from app import classifier, config, storage
from app.main import app
from app.masking import detokenise, mask_record, scrub_text
from tests.conftest import SAMPLE

client = TestClient(app)
H = {"X-API-Key": "test-key"}


# ---- masking ----
def test_mask_removes_phi_and_is_reversible_locally():
    masked, vault = mask_record(SAMPLE)
    blob = json.dumps(masked)
    for v in ("Jane Testcase", "1980-01-31", "XYZ998877"):
        assert v not in blob
    assert masked["patient_name"].startswith("[PATIENT_")
    assert detokenise(masked["patient_name"], vault) == "Jane Testcase"


def test_tokens_are_deterministic():
    assert mask_record(SAMPLE)[0]["member_id"] == mask_record(SAMPLE)[0]["member_id"]


def test_scrub_text():
    assert scrub_text("born 1990-05-05 ssn 123-45-6789") == "born [DATE] ssn [SSN]"


def test_llm_only_sees_masked_data(monkeypatch):
    seen = []
    monkeypatch.setattr(config, "LLM_API_KEY", "fake")
    monkeypatch.setattr(classifier.OpenAICompatibleProvider, "_chat",
                        lambda self, p: seen.append(p) or '{"category":"medical_necessity","action":"x","confidence":0.8}')
    r = client.post("/webhook/denial", json=SAMPLE, headers=H)
    assert r.status_code == 200 and r.json()["provider"] == "llm"
    assert seen and all("Jane Testcase" not in p and "XYZ998877" not in p for p in seen)


# ---- auth ----
def test_missing_key_401():
    assert client.post("/webhook/denial", json=SAMPLE).status_code == 401


def test_wrong_key_401():
    assert client.post("/webhook/denial", json=SAMPLE, headers={"X-API-Key": "nope"}).status_code == 401


def test_health_is_public():
    assert client.get("/health").json()["status"] == "ok"


# ---- classification ----
def test_rule_classification():
    p = classifier.RuleBasedProvider()
    assert p.classify({"carc_codes": ["197"]})["category"] == "authorization"
    assert p.classify({"carc_codes": ["16"]})["category"] == "missing_information"
    assert p.classify({"carc_codes": ["999"]})["category"] == "other"


def test_webhook_end_to_end():
    r = client.post("/webhook/denial", json=SAMPLE, headers=H)
    body = r.json()
    assert r.status_code == 200 and body["category"] == "medical_necessity"
    assert "Jane Testcase" in body["appeal_letter"]          # caller gets real letter
    stored = storage.get_result(body["record_id"])
    assert "Jane Testcase" not in stored["appeal_letter_masked"]  # DB keeps tokens only


def test_validation_rejects_bad_payload():
    assert client.post("/webhook/denial", json={"claim_id": "x"}, headers=H).status_code == 422


# ---- audit ----
def test_audit_written_without_phi():
    client.post("/webhook/denial", json=SAMPLE, headers=H)
    text = open(config.AUDIT_LOG_PATH).read()
    assert "denial_triaged" in text and "tester" in text
    for v in ("Jane Testcase", "1980-01-31", "XYZ998877", "test-key"):
        assert v not in text


def test_audit_is_append_only():
    storage.audit("tester", "x")
    import sqlite3, pytest
    with storage.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM audit")


def test_metrics_count():
    client.post("/webhook/denial", json=SAMPLE, headers=H)
    assert client.get("/metrics", headers=H).json()["denials_received"] >= 1
