"""Medical records & protected files (TRD §10/§13 API; AppFlow §5/§6).

Every retrieval authorizes BEFORE any byte is read/decrypted; successful and
denied access are audited; uploads run the full guarded lifecycle.
"""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import APIError
from ...core.security import ROLE_DOCTOR, ROLE_PATIENT
from ...db.session import get_db
from ...models.models import MedicalFiles, MedicalRecords, Permissions, Reports, Users
from ..deps import get_current_user
from ...services.audit import access_log, audit
from ...services.authorization import RESOURCE_RECORD, authorize_record_access
from ...services.files import read_and_decrypt, store_upload
from ...services.ledger_outbox import enqueue

router = APIRouter(tags=["records"])

VALID_RECORD_TYPES = {"BLOOD_REPORT", "XRAY", "PRESCRIPTION", "GENERAL", "SCAN"}


class RecordBody(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    record_type: str


@router.post("/records", status_code=201)
def create_record(body: RecordBody, user: Users = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    if user.role != ROLE_PATIENT:
        raise APIError(403, "FORBIDDEN")
    if body.record_type not in VALID_RECORD_TYPES:
        raise APIError(400, "VALIDATION_ERROR")
    record = MedicalRecords(patient_id=user.id, record_type=body.record_type,
                            title=body.title, status="ACTIVE")
    db.add(record)
    audit(db, actor_id=user.id, role=user.role, event_type="RECORD_CREATE",
          target_type=RESOURCE_RECORD, outcome="SUCCESS")
    db.commit()
    db.refresh(record)
    return _record_payload(db, record)


def _record_payload(db: Session, record: MedicalRecords) -> dict:
    files = db.execute(select(MedicalFiles).where(MedicalFiles.record_id == record.id)).scalars().all()
    reports = db.execute(select(Reports).where(Reports.record_id == record.id)).scalars().all()
    file_to_report = {r.file_id: r.id for r in reports}
    return {
        "id": record.id, "patient_id": record.patient_id, "record_type": record.record_type,
        "title": record.title, "status": record.status,
        "files": [{"id": f.id, "mime_type": f.mime_type, "size": f.size,
                   "checksum": f.checksum, "key_id": f.key_id, "key_version": f.key_version,
                   "report_id": file_to_report.get(f.id),
                   "created_at": f.created_at.isoformat()} for f in files],
        "reports": [{"id": r.id, "file_id": r.file_id, "title": r.title,
                     "status": r.status} for r in reports],
    }


@router.get("/records")
def list_records(user: Users = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> list:
    if user.role == ROLE_PATIENT:
        rows = db.execute(select(MedicalRecords).where(
            MedicalRecords.patient_id == user.id,
            MedicalRecords.status != "DELETED")).scalars().all()
    elif user.role == ROLE_DOCTOR:
        # Only explicitly authorized records (server-side scope, never route-derived).
        rows = db.execute(
            select(MedicalRecords)
            .join(Permissions, Permissions.resource_id == MedicalRecords.id)
            .where(
                Permissions.recipient_user_id == user.id,
                Permissions.status == "ACTIVE",
                MedicalRecords.status != "DELETED",
            )
        ).scalars().all()
    else:
        raise APIError(403, "FORBIDDEN")  # admins have no automatic clinical access
    return [_record_payload(db, r) for r in rows]


@router.get("/records/{record_id}")
def get_record(record_id: int, user: Users = Depends(get_current_user),
               request: Request = None, db: Session = Depends(get_db)) -> dict:
    record = authorize_record_access(db, user, record_id)
    access_log(db, actor_id=user.id, role=user.role, action="RECORD_VIEW",
               resource_type=RESOURCE_RECORD, resource_id=record.id, outcome="GRANTED")
    db.commit()
    return _record_payload(db, record)


@router.delete("/records/{record_id}")
def delete_record(record_id: int, user: Users = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    record = db.get(MedicalRecords, record_id)
    if record is None or record.status == "DELETED":
        raise APIError(404, "NOT_FOUND")
    if user.role != ROLE_PATIENT or record.patient_id != user.id:
        raise APIError(403, "FORBIDDEN")
    record.status = "DELETED"
    audit(db, actor_id=user.id, role=user.role, event_type="RECORD_DELETE",
          target_type=RESOURCE_RECORD, target_id=record.id, outcome="SUCCESS")
    db.commit()
    return {"status": "deleted", "id": record.id}


@router.post("/records/{record_id}/files", status_code=201)
async def upload_file(record_id: int, request: Request,
                      file: UploadFile = File(...), note: str | None = Form(default=None),
                      user: Users = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict:
    record = authorize_record_access(db, user, record_id, action="FILE_UPLOAD")
    if user.role != ROLE_PATIENT or record.patient_id != user.id:
        # Only the owning patient may add protected content.
        raise APIError(403, "FORBIDDEN")
    data = await file.read()
    mf = store_upload(db, record_id=record.id, filename=file.filename or "",
                      content_type=file.content_type or "", data=data)
    report = Reports(record_id=record.id, file_id=mf.id,
                     title=(mf.original_name or f"Report {mf.id}")[-255:],
                     type=record.record_type, status="ACTIVE")
    db.add(report)
    db.flush()
    audit(db, actor_id=user.id, role=user.role, event_type="FILE_UPLOAD",
          target_type="MEDICAL_FILE", target_id=mf.id, outcome="SUCCESS",
          details={"mime": mf.mime_type, "size": mf.size,
                   "scan": getattr(mf, "_scan", None)})
    db.commit()
    return {"id": mf.id, "record_id": mf.record_id, "report_id": report.id,
            "mime_type": mf.mime_type, "size": mf.size, "checksum": mf.checksum,
            "key_id": mf.key_id, "key_version": mf.key_version}


def _download(db: Session, user: Users, record_id: int, file_id: int | None) -> Response:
    record = authorize_record_access(db, user, record_id, action="FILE_DOWNLOAD")
    q = select(MedicalFiles).where(MedicalFiles.record_id == record.id)
    if file_id is not None:
        q = q.where(MedicalFiles.id == file_id)
    mf = db.execute(q.order_by(MedicalFiles.id.desc())).scalars().first()
    if mf is None:
        raise APIError(404, "NOT_FOUND")
    data = read_and_decrypt(db, mf)  # authorization already passed
    access_log(db, actor_id=user.id, role=user.role, action="FILE_DOWNLOAD",
               resource_type="MEDICAL_FILE", resource_id=mf.id, outcome="GRANTED",
               details={"record_id": record.id})
    audit_row = audit(db, actor_id=user.id, role=user.role, event_type="FILE_DOWNLOAD",
                      target_type="MEDICAL_FILE", target_id=mf.id, outcome="SUCCESS")
    # ACCESS decision reference — opaque, no medical payload (TRD §17).
    enqueue(db, event_type="ACCESS", ref=f"file:{mf.id}", audit_event_id=audit_row.id,
            data={"action": "FILE_DOWNLOAD", "outcome": "GRANTED",
                  "resource": f"record:{record.id}"})
    db.commit()
    from fastapi.responses import Response as FastAPIResponse
    return FastAPIResponse(content=data, media_type=mf.mime_type,
                           headers={"Content-Disposition":
                                    f'attachment; filename="protected-{mf.id}.bin"',
                                    "Cache-Control": "no-store"})


@router.get("/records/{record_id}/download")
def download_record_file(record_id: int, file_id: int | None = None,
                         user: Users = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> Response:
    return _download(db, user, record_id, file_id)


@router.get("/files/{file_id}/download")
def download_file(file_id: int, user: Users = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> Response:
    mf = db.get(MedicalFiles, file_id)
    if mf is None:
        raise APIError(404, "NOT_FOUND")
    return _download(db, user, mf.record_id, mf.id)
