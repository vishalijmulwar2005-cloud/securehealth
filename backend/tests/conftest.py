"""Test environment: temp SQLite (documented dev/test convenience), temp
protected storage, stub scanner, deterministic secrets. Production guards
are exercised separately."""
import base64
import os
import tempfile

TEST_DIR = tempfile.mkdtemp(prefix="sh_test_")
os.environ["SECUREHEALTH_ENV"] = "test"
os.environ["SECUREHEALTH_DATABASE_URL"] = f"sqlite:///{TEST_DIR}/test.db"
os.environ["SECUREHEALTH_STORAGE_ROOT"] = f"{TEST_DIR}/protected_storage"
os.environ["SECUREHEALTH_QUARANTINE_ROOT"] = f"{TEST_DIR}/quarantine"
os.environ["SECUREHEALTH_JWT_SECRET"] = "test-secret-key"
os.environ["SECUREHEALTH_FILE_KEYS"] = '{"t1": "%s"}' % base64.urlsafe_b64encode(b"T" * 32).decode()
os.environ["SECUREHEALTH_ACTIVE_FILE_KEY_ID"] = "t1"
os.environ["SECUREHEALTH_SECURITY_SCAN_MODE"] = "stub"
os.environ["SECUREHEALTH_PSEUDO_SECRET"] = "test-pseudo-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.rate_limit import limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    limiter.clear()
    with TestClient(app) as c:
        yield c


def register_and_login(client, email, role="PATIENT", password="TestPass#123"):
    body = {"email": email, "password": password, "full_name": email.split("@")[0],
            "role": role}
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# Minimal valid payloads for the allowlisted types
PDF_BYTES = b"%PDF-1.4\n%test\n" + b"A" * 256
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"B" * 256
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"C" * 256
DICOM_BYTES = b"\x00" * 128 + b"DICM" + b"D" * 256
EXE_BYTES = b"MZ\x90\x00" + b"E" * 256
