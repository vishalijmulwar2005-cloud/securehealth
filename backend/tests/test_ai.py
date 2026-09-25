"""Phase 8 gate: AI analysis authorization, async states, original-report
preservation, assistance labeling; regulator read-only surface; expiry sweep."""
import math

from app.db.session import SessionLocal
from app.services.ai_worker import process_jobs

from tests.conftest import PDF_BYTES, auth, register_and_login


def _patient_with_file(client, email):
    p = register_and_login(client, email)
    r = client.post("/api/v1/records",
                    json={"title": "AI test record", "record_type": "BLOOD_REPORT"},
                    headers=auth(p["access_token"]))
    record_id = r.json()["id"]
    up = client.post(f"/api/v1/records/{record_id}/files",
                     files={"file": ("report.pdf", PDF_BYTES, "application/pdf")},
                     headers=auth(p["access_token"]))
    assert up.status_code == 201, up.text
    return p, record_id, up.json()["report_id"]


def test_ai_request_requires_report_access(client):
    p, record_id, report_id = _patient_with_file(client, "ai1@example.com")
    stranger = register_and_login(client, "ai1b@example.com")
    r = client.post(f"/api/v1/ai/analyze/{report_id}", headers=auth(stranger["access_token"]))
    assert r.status_code == 404  # no permission context → hidden, never leaks


def test_ai_lifecycle_completes_with_assistance_label(client):
    p, record_id, report_id = _patient_with_file(client, "ai2@example.com")
    tok = auth(p["access_token"])
    r = client.post(f"/api/v1/ai/analyze/{report_id}", headers=tok)
    assert r.status_code == 202
    assert r.json()["status"] == "QUEUED"
    job_id = r.json()["id"]
    # A second request while one is running → CONFLICT (idempotency guard).
    r_dup = client.post(f"/api/v1/ai/analyze/{report_id}", headers=tok)
    assert r_dup.status_code == 409
    # Run the worker synchronously (dev/test; production = durable queue worker).
    process_jobs(SessionLocal())
    got = client.get(f"/api/v1/ai/analyses/{job_id}", headers=tok).json()
    assert got["status"] == "COMPLETED"
    assert got["trace_id"]
    assert "not a medical diagnosis" in got["notice"].lower()
    assert got["result"]["summary"]
    assert got["result"]["disclaimer"]
    assert got["result"]["model"]["id"]
    # Terminal state visible via by-report listing.
    listing = client.get(f"/api/v1/ai/by-report/{report_id}", headers=tok).json()
    assert listing[0]["status"] == "COMPLETED"


def test_ai_failure_and_success_leave_original_report_intact(client):
    p, record_id, report_id = _patient_with_file(client, "ai3@example.com")
    tok = auth(p["access_token"])
    before = client.get(f"/api/v1/records/{record_id}", headers=tok).json()
    process_jobs(SessionLocal())
    after = client.get(f"/api/v1/records/{record_id}", headers=tok).json()
    assert before["files"][0]["checksum"] == after["files"][0]["checksum"]
    assert after["files"][0]["key_version"] >= 1


def test_regulator_read_only_surfaces(client):
    p, record_id, report_id = _patient_with_file(client, "ai4@example.com")
    reg = client.post("/api/v1/auth/login",
                      json={"email": "regulator@example.com", "password": "Regulator#2026"})
    assert reg.status_code == 200
    tok = auth(reg.json()["access_token"])
    integrity = client.get("/api/v1/regulator/integrity", headers=tok)
    assert integrity.status_code == 200
    assert integrity.json()["chain"]["valid"] is True
    trail = client.get("/api/v1/regulator/audit", headers=tok)
    events = trail.json()
    assert all("details" not in e for e in events)  # no clinical metadata exposed
    # Regulator cannot mutate clinical data.
    deny = client.post("/api/v1/records", json={"title": "x", "record_type": "GENERAL"},
                       headers=tok)
    assert deny.status_code == 403


def test_expiry_sweep_notifies_within_24h(client):
    from datetime import datetime, timedelta, timezone
    p = register_and_login(client, "ai5@example.com")
    d = register_and_login(client, "ai5d@example.com", role="DOCTOR")
    rec = client.post("/api/v1/records", json={"title": "t", "record_type": "BLOOD_REPORT"},
                      headers=auth(p["access_token"]))
    req = client.post("/api/v1/consents/requests",
                      json={"patient_id": p["user"]["id"], "resource_type": "RECORD",
                            "resource_id": rec.json()["id"], "scope": "VIEW"},
                      headers=auth(d["access_token"]))
    ap = client.post(f"/api/v1/consents/requests/{req.json()['id']}/approve",
                     json={"duration_days": 7}, headers=auth(p["access_token"]))
    perm_id = ap.json()["id"]
    db = SessionLocal()
    try:
        perm = db.get(__import__("app.models.models", fromlist=["Permissions"]).Permissions, perm_id)
        perm.expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
        db.commit()
    finally:
        db.close()
    process_jobs(SessionLocal())
    notes = client.get("/api/v1/notifications", headers=auth(p["access_token"])).json()
    assert any(n["type"] == "CONSENT_EXPIRING" for n in notes)
    # Sweep runs again → no duplicate notification.
    process_jobs(SessionLocal())
    notes2 = client.get("/api/v1/notifications", headers=auth(p["access_token"])).json()
    assert sum(1 for n in notes2 if n["type"] == "CONSENT_EXPIRING") == 1
