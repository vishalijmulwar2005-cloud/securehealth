"""G5 Files gate: type/size/empty/magic/path-traversal validation, quarantine/
scan enforcement, encryption at rest, authorized retrieval, checksum integrity."""
import base64
import os

from tests.conftest import (
    DICOM_BYTES, EXE_BYTES, JPEG_BYTES, PDF_BYTES, PNG_BYTES, auth, register_and_login,
)


def _upload(client, token, record_id, filename, content_type, data):
    return client.post(
        f"/api/v1/records/{record_id}/files",
        files={"file": (filename, data, content_type)},
        headers=auth(token),
    )


def _patient_with_record(client, email):
    p = register_and_login(client, email)
    r = client.post("/api/v1/records",
                    json={"title": "Reports", "record_type": "GENERAL"},
                    headers=auth(p["access_token"]))
    assert r.status_code == 201
    return p, r.json()["id"]


def test_upload_all_allowlisted_types(client):
    p, record_id = _patient_with_record(client, "f1@example.com")
    tok = p["access_token"]
    for filename, ctype, data in [
        ("report.pdf", "application/pdf", PDF_BYTES),
        ("scan.png", "image/png", PNG_BYTES),
        ("photo.jpg", "image/jpeg", JPEG_BYTES),
        ("study.dcm", "application/dicom", DICOM_BYTES),
    ]:
        r = _upload(client, tok, record_id, filename, ctype, data)
        assert r.status_code == 201, (filename, r.text)
        body = r.json()
        assert body["key_id"] and body["key_version"] >= 1  # key metadata recorded
        assert len(body["checksum"]) == 64  # SHA-256


def test_reject_exe_and_mime_mismatch(client):
    p, record_id = _patient_with_record(client, "f2@example.com")
    tok = p["access_token"]
    r = _upload(client, tok, record_id, "evil.exe", "application/octet-stream", EXE_BYTES)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    # wrong-MIME: png bytes declared as pdf (magic mismatch)
    r2 = _upload(client, tok, record_id, "fake.pdf", "application/pdf", PNG_BYTES)
    assert r2.status_code == 400


def test_reject_empty_file(client):
    p, record_id = _patient_with_record(client, "f3@example.com")
    r = _upload(client, p["access_token"], record_id, "empty.pdf", "application/pdf", b"")
    assert r.status_code == 400


def test_reject_oversized_file(client):
    p, record_id = _patient_with_record(client, "f4@example.com")
    big = b"%PDF-1.4\n" + b"X" * (26 * 1024 * 1024)
    r = _upload(client, p["access_token"], record_id, "big.pdf", "application/pdf", big)
    assert r.status_code == 400


def test_bytes_stored_encrypted_outside_public_root(client):
    p, record_id = _patient_with_record(client, "f5@example.com")
    r = _upload(client, p["access_token"], record_id, "report.pdf",
                "application/pdf", PDF_BYTES)
    file_id = r.json()["id"]
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.models import MedicalFiles
    db = SessionLocal()
    try:
        mf = db.get(MedicalFiles, file_id)
        path = os.path.join(settings.STORAGE_ROOT, mf.storage_reference.replace("/", os.sep))
        with open(path, "rb") as fh:
            stored = fh.read()
    finally:
        db.close()
    # Stored bytes are ciphertext: plaintext and its magic must not appear.
    assert PDF_BYTES[:8] not in stored
    assert b"%PDF" not in stored
    assert os.path.commonpath([os.path.abspath(settings.STORAGE_ROOT)]) in os.path.abspath(path)


def test_download_requires_authorization_and_returns_plaintext(client):
    p, record_id = _patient_with_record(client, "f6@example.com")
    up = _upload(client, p["access_token"], record_id, "report.pdf",
                 "application/pdf", PDF_BYTES)
    file_id = up.json()["id"]
    ok = client.get(f"/api/v1/files/{file_id}/download", headers=auth(p["access_token"]))
    assert ok.status_code == 200
    assert ok.content == PDF_BYTES  # decrypted + checksum-verified
    stranger = register_and_login(client, "f6b@example.com")
    denied = client.get(f"/api/v1/files/{file_id}/download", headers=auth(stranger["access_token"]))
    assert denied.status_code == 404  # no context -> hidden


def test_scan_failure_blocks_availability(client, monkeypatch):
    monkeypatch.setenv("SECUREHEALTH_SECURITY_SCAN_FAIL", "1")
    from app.core.config import settings as s
    s.SECURITY_SCAN_FAIL = "1"
    p, record_id = _patient_with_record(client, "f7@example.com")
    r = _upload(client, p["access_token"], record_id, "report.pdf",
                "application/pdf", PDF_BYTES)
    s.SECURITY_SCAN_FAIL = ""
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    listing = client.get("/api/v1/records", headers=auth(p["access_token"]))
    assert all(not rec["files"] for rec in listing.json())  # no orphaned metadata


def test_key_rotation_keeps_old_files_decryptable(client):
    """old encrypted file + recorded old key version + authorized retrieval =
    successful controlled decryption (Security & DB §7)."""
    p, record_id = _patient_with_record(client, "f8@example.com")
    up = _upload(client, p["access_token"], record_id, "v1.pdf", "application/pdf", PDF_BYTES)
    file_id = up.json()["id"]
    from app.core.config import settings as s
    # Rotate: introduce a new active key version.
    new_key = base64.urlsafe_b64encode(b"U" * 32).decode()
    s.FILE_KEYS["t2"] = new_key
    s.ACTIVE_FILE_KEY_ID = "t2"
    try:
        ok = client.get(f"/api/v1/files/{file_id}/download", headers=auth(p["access_token"]))
        assert ok.status_code == 200
        assert ok.content == PDF_BYTES
        # New upload uses the new key id.
        up2 = _upload(client, p["access_token"], record_id, "v2.pdf",
                      "application/pdf", PDF_BYTES)
        assert up2.json()["key_id"] == "t2"
    finally:
        s.ACTIVE_FILE_KEY_ID = "t1"
