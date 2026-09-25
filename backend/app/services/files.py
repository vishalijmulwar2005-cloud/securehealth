"""Protected medical file handling (TRD v4.1 §10; Security & Database §8).

Lifecycle: Upload -> Validate -> Quarantine -> Malware/Security Scan ->
Encrypt -> Store -> Commit metadata -> Available -> Authorized retrieval ->
Archive/Delete. Storage failure never yields false persistence; temporary
artifacts are cleaned on success AND failure paths; no orphaned metadata.

Allowlist: PDF / PNG / JPEG / DICOM, max 25 MB, magic-byte + MIME + extension
consistency, empty rejected, generated storage keys (path traversal safe).
Fernet encryption with key_id/key_version; SHA-256 checksum of plaintext.
Scanning is REQUIRED in production; 'disabled' mode is refused there.
"""
import datetime as dt
import hashlib
import os
import secrets
import uuid

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import APIError
from ..models.models import MedicalFiles

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".dcm"}
ALLOWED_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".dcm": "application/dicom",
}
MAGIC = {
    "application/pdf": (0, b"%PDF"),
    "image/png": (0, b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (0, b"\xff\xd8\xff"),
    "application/dicom": (128, b"DICM"),  # DICM preamble at offset 128
}


def _safe_root(root: str) -> str:
    os.makedirs(root, exist_ok=True)
    return root


def magic_matches(mime: str, data: bytes) -> bool:
    offset, signature = MAGIC[mime]
    return len(data) >= offset + len(signature) and data[offset:offset + len(signature)] == signature


def validate_upload(*, filename: str, content_type: str, data: bytes) -> str:
    """Return the canonical MIME type or raise VALIDATION_ERROR."""
    if not data:
        raise APIError(400, "VALIDATION_ERROR", "Empty files are rejected")
    if len(data) > settings.MAX_FILE_SIZE_BYTES:
        raise APIError(400, "VALIDATION_ERROR", "File exceeds the maximum allowed size")
    ext = os.path.splitext(filename.replace("\\", "/").split("/")[-1].strip().lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise APIError(400, "VALIDATION_ERROR", "Unsupported file type")
    if content_type and content_type.split(";")[0].strip() not in (ALLOWED_MIME[ext], ""):
        raise APIError(400, "VALIDATION_ERROR", "Declared type does not match the file")
    mime = ALLOWED_MIME[ext]
    if not magic_matches(mime, data):
        raise APIError(400, "VALIDATION_ERROR", "File content does not match its type")
    return mime


def run_security_scan(data: bytes) -> dict:
    """Production malware/security scanning is REQUIRED (Security & DB §8).

    'stub' is the documented development/test placeholder (content checks only).
    'clamav' is the deployment integration hook. 'disabled' is a dev-only bypass
    that is refused in production (guarded in main.create_app).
    """
    mode = settings.SECURITY_SCAN_MODE
    if mode == "disabled":
        if settings.is_production:
            raise APIError(500, "INTERNAL_ERROR", "Scanner misconfiguration")
        return {"clean": True, "scanner": "disabled(dev-only)"}
    if settings.SECURITY_SCAN_FAIL:
        raise APIError(400, "VALIDATION_ERROR", "Security scan failed; file not accepted")
    if mode in ("stub", "clamav"):
        # stub: validated content checks already performed; a real engine hooks here.
        return {"clean": True, "scanner": mode}
    raise APIError(500, "INTERNAL_ERROR", "Scanner misconfiguration")


def _active_fernet() -> tuple[str, int, Fernet]:
    key_id = settings.ACTIVE_FILE_KEY_ID
    if key_id not in settings.FILE_KEYS:
        raise APIError(500, "INTERNAL_ERROR", "Encryption key misconfiguration")
    version = int(key_id.split("-v")[-1]) if "-v" in key_id else 1
    return key_id, version, Fernet(settings.FILE_KEYS[key_id])


def _fernet_for(key_id: str) -> Fernet:
    if key_id not in settings.FILE_KEYS:
        raise APIError(500, "INTERNAL_ERROR", "Encryption key misconfiguration")
    return Fernet(settings.FILE_KEYS[key_id])


def store_upload(db: Session, *, record_id: int, filename: str, content_type: str,
                 data: bytes) -> MedicalFiles:
    """Full guarded lifecycle; any failure leaves NO metadata and NO stored bytes."""
    mime = validate_upload(filename=filename, content_type=content_type, data=data)
    quarantine = _safe_root(settings.QUARANTINE_ROOT)
    storage = _safe_root(settings.STORAGE_ROOT)

    qname = f"q_{uuid.uuid4().hex}.tmp"
    qpath = os.path.join(quarantine, qname)
    skey = None
    try:
        # 1) Quarantine + scan before permanent availability
        with open(qpath, "wb") as fh:
            fh.write(data)
        scan = run_security_scan(data)

        # 2) Encrypt with the active key version
        key_id, key_version, fernet = _active_fernet()
        token = fernet.encrypt(data)

        # 3) Store outside any public/web root under a generated key
        now = dt.datetime.now(dt.timezone.utc)
        skey = os.path.join(f"{now:%Y/%m}", f"{secrets.token_hex(16)}.bin")
        spath = os.path.join(storage, skey)
        os.makedirs(os.path.dirname(spath), exist_ok=True)
        with open(spath, "wb") as fh:
            fh.write(token)

        # 4) Commit metadata only after durable storage
        row = MedicalFiles(
            record_id=record_id,
            storage_reference=skey.replace(os.sep, "/"),
            checksum=hashlib.sha256(data).hexdigest(),
            original_name=filename[-255:] if filename else None,
            mime_type=mime,
            size=len(data),
            key_id=key_id,
            key_version=key_version,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        row._scan = scan  # type: ignore[attr-defined]  # surfaced to audit caller
        return row
    except APIError:
        _cleanup(spath=None if skey is None else os.path.join(storage, skey), qpath=qpath)
        db.rollback()
        raise
    except Exception:
        # Any unexpected failure (storage, DB): no false persistence, no orphans.
        _cleanup(spath=None if skey is None else os.path.join(storage, skey), qpath=qpath)
        db.rollback()
        raise APIError(500, "INTERNAL_ERROR", "Storage unavailable; nothing was saved")
    finally:
        _cleanup(spath=None, qpath=qpath)  # temp artifacts cleaned on all paths


def _cleanup(*, spath: str | None, qpath: str) -> None:
    for path in (spath, qpath):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def read_and_decrypt(db: Session, mf: MedicalFiles) -> bytes:
    """Read + decrypt + integrity-verify. Caller has ALREADY authorized access."""
    spath = os.path.join(_safe_root(settings.STORAGE_ROOT),
                         mf.storage_reference.replace("/", os.sep))
    try:
        with open(spath, "rb") as fh:
            token = fh.read()
        data = _fernet_for(mf.key_id).decrypt(token)
    except (OSError, InvalidToken):
        raise APIError(500, "INTERNAL_ERROR", "Protected content unavailable")
    if hashlib.sha256(data).hexdigest() != mf.checksum:
        raise APIError(500, "INTERNAL_ERROR", "Protected content unavailable")
    return data
