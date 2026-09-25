"""Background jobs (dev/test in-process worker; production runs the same jobs
on the durable Celery queue — TRD §4/§18 tracked gap):

1. AI analysis jobs:  QUEUED → PROCESSING → COMPLETED | FAILED.
   - Bounded retries (max 2 attempts) then FAILED with a safe category.
   - Original report is never touched; result artifact stored protected.
2. Consent-expiry sweep: one CONSENT_EXPIRING notification per permission as
   it enters its last 24 h (spec: async sweep + lazy enforcement).
"""
import datetime
import json
import os
import threading
from datetime import timedelta

from sqlalchemy import select

from ..core.config import settings
from ..db.session import SessionLocal
from ..models.models import AiAnalyses, Notifications, Permissions, ResearchConsents
from .ai_engine import analyze_report, result_json_bytes
from .audit import utcnow
from .files import read_and_decrypt
from .ledger_outbox import enqueue

MAX_ATTEMPTS = 2
AI_ATTEMPTS: dict[int, int] = {}  # job id -> attempts (bounded retry ledger)

_lock = threading.Lock()
_worker_started = False


def _save_result(job_id: int, result: dict) -> str:
    rel = os.path.join("ai_results", f"{job_id}.json")
    path = os.path.join(settings.STORAGE_ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(result_json_bytes(result))
    return rel.replace(os.sep, "/")


def load_result(job_id: int, reference: str) -> dict | None:
    path = os.path.join(settings.STORAGE_ROOT, reference.replace("/", os.sep))
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _process_ai_jobs(db) -> None:
    rows = db.execute(select(AiAnalyses).where(
        AiAnalyses.status == "QUEUED").order_by(AiAnalyses.id)).scalars().all()
    for job in rows:
        job.status = "PROCESSING"
        db.commit()  # claim is durable before work starts
        attempts = AI_ATTEMPTS.get(job.id, 0) + 1
        AI_ATTEMPTS[job.id] = attempts
        try:
            from ..models.models import MedicalFiles, MedicalRecords, Reports
            report = db.get(Reports, job.report_id)
            record = db.get(MedicalRecords, report.record_id) if report else None
            file_row = db.execute(select(MedicalFiles).where(
                MedicalFiles.record_id == report.record_id).order_by(
                MedicalFiles.id.desc())).scalars().first() if report else None
            if report is None or record is None:
                job.status = "FAILED"
                job.failure_category = "REPORT_NOT_FOUND"
                db.commit()
                continue
            # Read (authorized context: worker acts on behalf of requester) and
            # compute a content fingerprint WITHOUT storing report content.
            if file_row is not None:
                data = read_and_decrypt(db, file_row)
                content_hash = len(data)  # read proves decryptability; size feeds metrics
            else:
                content_hash = 0
            result = analyze_report(report={
                "mime_type": file_row.mime_type if file_row else "application/pdf",
                "size": file_row.size if file_row else content_hash,
                "checksum": file_row.checksum if file_row else "unavailable",
                "record_type": record.record_type, "title": record.title,
                "trace_id": job.trace_id or f"ai-{job.id}",
            })
            reference = _save_result(job.id, result)
            job.status = "COMPLETED"
            job.model_id = result["model"]["id"]
            job.model_version = result["model"]["version"]
            job.prompt_version = result["model"]["prompt_version"]
            job.result_reference = reference
            db.add(Notifications(
                user_id=job.requested_by, type="AI_COMPLETED",
                title="AI-assisted analysis is ready for review",
                message="Open the record to review it with the original report."))
            db.commit()
        except Exception as exc:  # bounded retry, then truthful failure
            db.rollback()
            job = db.get(AiAnalyses, job.id)
            if attempts >= MAX_ATTEMPTS:
                job.status = "FAILED"
                job.failure_category = "ANALYSIS_FAILED"
                db.commit()
            else:
                job.status = "QUEUED"
                db.commit()


def _sweep_expiring_permissions(db) -> None:
    """Notify patients of permissions entering their last 24 h (once each)."""
    now = utcnow()
    horizon = now + timedelta(hours=24)
    rows = db.execute(select(Permissions).where(Permissions.status == "ACTIVE")).scalars().all()
    for perm in rows:
        if perm.expires_at is None:
            continue
        exp = perm.expires_at if perm.expires_at.tzinfo else perm.expires_at.replace(tzinfo=now.tzinfo)
        if exp > horizon:
            continue
        existing = db.execute(select(Notifications.id).where(
            Notifications.user_id == perm.patient_id,
            Notifications.type == "CONSENT_EXPIRING",
            Notifications.message.contains(f"permission-{perm.id}"))).scalars().first()
        if existing is None:
            db.add(Notifications(
                user_id=perm.patient_id, type="CONSENT_EXPIRING",
                title="A permission is approaching expiry",
                message=f"permission-{perm.id} expires within 24 hours."))
    # Also sweep research consents past expiry → EXPIRED (authoritative state).
    for rc in db.execute(select(ResearchConsents).where(
            ResearchConsents.status == "ACTIVE")).scalars().all():
        if rc.expires_at is not None and rc.expires_at < now:
            rc.status = "EXPIRED"
            rc.revoked_at = now
    db.commit()


def process_jobs(db) -> dict:
    """One synchronous pass — used by tests and the thread loop."""
    with _lock:
        _process_ai_jobs(db)
        _sweep_expiring_permissions(db)
        from .ledger_outbox import process_outbox
        mined = process_outbox(db)
        return {"mined": mined}


def start_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    _worker_started = True

    def loop() -> None:
        import time
        while True:
            db = SessionLocal()
            try:
                _process_ai_jobs(db)
                _sweep_expiring_permissions(db)
            except Exception:
                db.rollback()
            finally:
                # IMPORTANT: end the read transaction every pass. Without this,
                # SQLite (and repeatable-read databases) keep the worker pinned
                # to a stale snapshot and it never sees newly queued jobs.
                db.rollback()
                db.close()
            time.sleep(1.0)

    threading.Thread(target=loop, name="ai-jobs-worker", daemon=True).start()
