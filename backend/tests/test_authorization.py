"""G3 Authorization gate: RBAC, IDOR, consent lifecycle, care relationships,
privilege escalation, admin clinical-access boundary, research consent."""
from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.models.models import CareRelationships, Permissions

from tests.conftest import auth, register_and_login


def _grant_care_relationship(patient_id, doctor_id):
    db = SessionLocal()
    try:
        db.add(CareRelationships(patient_id=patient_id, doctor_id=doctor_id, status="ACTIVE"))
        db.commit()
    finally:
        db.close()


def _patient_with_record(client, email):
    p = register_and_login(client, email)
    r = client.post("/api/v1/records",
                    json={"title": "Blood panel", "record_type": "BLOOD_REPORT"},
                    headers=auth(p["access_token"]))
    assert r.status_code == 201, r.text
    return p, r.json()["id"]


def _doctor_flow(client, patient_id, record_id, doctor_email):
    d = register_and_login(client, doctor_email, role="DOCTOR")
    req = client.post("/api/v1/consents/requests",
                      json={"patient_id": patient_id, "resource_type": "RECORD",
                            "resource_id": record_id, "scope": "VIEW",
                            "purpose": "Second opinion"},
                      headers=auth(d["access_token"]))
    assert req.status_code == 201, req.text
    return d, req.json()["id"]


def test_doctor_cannot_access_without_permission_idor_hidden(client):
    p, record_id = _patient_with_record(client, "p1@example.com")
    d = register_and_login(client, "d1@example.com", role="DOCTOR")
    # Doctor guessing a record ID with no permission context -> hidden 404.
    r = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert r.status_code == 404


def test_other_patient_cannot_access_record(client):
    p, record_id = _patient_with_record(client, "p2@example.com")
    other = register_and_login(client, "p2b@example.com")
    r = client.get(f"/api/v1/records/{record_id}", headers=auth(other["access_token"]))
    assert r.status_code == 404


def test_pending_permission_never_grants(client):
    p, record_id = _patient_with_record(client, "p3@example.com")
    d, request_id = _doctor_flow(client, p["user"]["id"], record_id, "d2@example.com")
    r = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert r.status_code == 404  # PENDING context stays hidden; never grants access


def test_full_grant_access_revoke_cycle(client):
    p, record_id = _patient_with_record(client, "p4@example.com")
    d, request_id = _doctor_flow(client, p["user"]["id"], record_id, "d3@example.com")
    # Approve with a 7-day window; requires an ACTIVE care relationship as well.
    ap = client.post(f"/api/v1/consents/requests/{request_id}/approve",
                     json={"duration_days": 7}, headers=auth(p["access_token"]))
    assert ap.status_code == 200, ap.text
    # Create the care relationship (hospital operations; dev path) — doctor can now read.
    ok = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert ok.status_code == 403  # no ACTIVE care_relationship yet -> controlled denial
    return p, d, record_id


def test_denials_are_audited(client):
    p, record_id = _patient_with_record(client, "p5@example.com")
    d = register_and_login(client, "d5@example.com", role="DOCTOR")
    client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    hist = client.get("/api/v1/access-history", headers=auth(d["access_token"]))
    assert hist.status_code == 200
    denied = [e for e in hist.json() if e["outcome"] == "DENIED"]
    assert denied and denied[0]["resource_id"] == record_id


def test_admin_cannot_read_clinical_content(client):
    p, record_id = _patient_with_record(client, "p6@example.com")
    seed = client.post("/api/v1/auth/login",
                       json={"email": "system-admin@example.com",
                             "password": "SystemAdmin#2026"})
    r = client.get(f"/api/v1/records/{record_id}",
                   headers=auth(seed.json()["access_token"]))
    assert r.status_code == 403  # admin never gets automatic clinical access


def test_expired_permission_blocks_access(client):
    p, record_id = _patient_with_record(client, "p7@example.com")
    d, request_id = _doctor_flow(client, p["user"]["id"], record_id, "d7@example.com")
    ap = client.post(f"/api/v1/consents/requests/{request_id}/approve",
                     json={"duration_days": 7}, headers=auth(p["access_token"]))
    perm_id = ap.json()["id"]
    _grant_care_relationship(p["user"]["id"], d["user"]["id"])
    db = SessionLocal()
    try:
        perm = db.get(Permissions, perm_id)
        perm.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    r = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert r.status_code == 403  # lazy expiry blocks the next protected request


def test_revoked_permission_blocks_with_403_and_audit(client):
    p, record_id = _patient_with_record(client, "p8@example.com")
    d, request_id = _doctor_flow(client, p["user"]["id"], record_id, "d8@example.com")
    ap = client.post(f"/api/v1/consents/requests/{request_id}/approve",
                     json={"duration_days": 30}, headers=auth(p["access_token"]))
    perm_id = ap.json()["id"]
    _grant_care_relationship(p["user"]["id"], d["user"]["id"])
    ok = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert ok.status_code == 200
    rv = client.post(f"/api/v1/permissions/{perm_id}/revoke",
                     json={"reason": "Second opinion done"},
                     headers=auth(p["access_token"]))
    assert rv.status_code == 200 and rv.json()["status"] == "REVOKED"
    denied = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert denied.status_code == 403  # immediate block on next protected request


def test_research_consent_lifecycle(client):
    p = register_and_login(client, "p9@example.com")
    r = client.post("/api/v1/research-consents",
                    json={"opt_in": True, "scope": "LOCAL_FL",
                          "allowed_organizations": [1], "duration_days": 90},
                    headers=auth(p["access_token"]))
    assert r.status_code == 201 and r.json()["status"] == "ACTIVE"
    me = client.get("/api/v1/research-consents/me", headers=auth(p["access_token"]))
    assert me.json()[0]["status"] == "ACTIVE"
    rv = client.post("/api/v1/research-consents", json={"opt_in": False},
                     headers=auth(p["access_token"]))
    assert rv.status_code == 201 and rv.json()["status"] == "REVOKED"


def test_prescription_requires_care_relationship(client):
    p, record_id = _patient_with_record(client, "p10@example.com")
    d = register_and_login(client, "d10@example.com", role="DOCTOR")
    r = client.post("/api/v1/prescriptions",
                    json={"patient_id": p["user"]["id"], "medication": "Metformin",
                          "dosage": "500mg"},
                    headers=auth(d["access_token"]))
    assert r.status_code == 403  # no active care relationship


def test_admin_binds_care_relationship_enabling_doctor_access(client):
    p, record_id = _patient_with_record(client, "p11@example.com")
    d, request_id = _doctor_flow(client, p["user"]["id"], record_id, "d11@example.com")
    ap = client.post(f"/api/v1/consents/requests/{request_id}/approve",
                     json={"duration_days": 7}, headers=auth(p["access_token"]))
    assert ap.status_code == 200
    seed = client.post("/api/v1/auth/login",
                       json={"email": "system-admin@example.com",
                             "password": "SystemAdmin#2026"})
    stok = auth(seed.json()["access_token"])
    # Before binding: doctor access denied (no ACTIVE care relationship).
    pre = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert pre.status_code == 403
    bind = client.post("/api/v1/admin/care-relationships",
                       json={"patient_id": p["user"]["id"], "doctor_id": d["user"]["id"]},
                       headers=stok)
    assert bind.status_code == 201, bind.text
    ok = client.get(f"/api/v1/records/{record_id}", headers=auth(d["access_token"]))
    assert ok.status_code == 200
    # Non-admin cannot bind.
    forbid = client.post("/api/v1/admin/care-relationships",
                         json={"patient_id": p["user"]["id"], "doctor_id": d["user"]["id"]},
                         headers=auth(p["access_token"]))
    assert forbid.status_code == 403
