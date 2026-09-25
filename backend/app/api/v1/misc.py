"""Notifications, prescriptions, access history, admin and health endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import APIError
from ...core.security import ROLE_DOCTOR, ROLE_PATIENT, ROLE_SYSTEM_ADMIN
from ...db.session import get_db
from ...models.models import (
    ACCOUNT_STATUSES, AccessLogs, MedicalRecords, Notifications, Prescriptions, Users,
)
from ..deps import get_current_user, require_system_admin
from ...services.audit import audit, utcnow
from ...services.authorization import has_active_care_relationship

router = APIRouter(tags=["care"])


# ---------- Notifications ----------

@router.get("/notifications")
def list_notifications(user: Users = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> list:
    rows = db.execute(select(Notifications).where(
        Notifications.user_id == user.id).order_by(Notifications.created_at.desc())).scalars().all()
    return [{"id": n.id, "type": n.type, "title": n.title, "message": n.message,
             "read": n.read, "read_at": n.read_at.isoformat() if n.read_at else None,
             "created_at": n.created_at.isoformat()} for n in rows]


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, user: Users = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    row = db.get(Notifications, notification_id)
    if row is None or row.user_id != user.id:
        raise APIError(404, "NOT_FOUND")
    if not row.read:
        row.read = True
        row.read_at = utcnow()
    db.commit()
    return {"id": row.id, "read": row.read}


# ---------- Prescriptions ----------

class PrescriptionBody(BaseModel):
    patient_id: int
    record_id: int | None = None
    medication: str = Field(min_length=1, max_length=255)
    dosage: str | None = Field(default=None, max_length=128)
    instructions: str | None = Field(default=None, max_length=512)


@router.post("/prescriptions", status_code=201)
def create_prescription(body: PrescriptionBody, user: Users = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    if user.role != ROLE_DOCTOR:
        raise APIError(403, "FORBIDDEN")
    patient = db.get(Users, body.patient_id)
    if patient is None or patient.role != ROLE_PATIENT:
        raise APIError(404, "NOT_FOUND")
    # Prescription requires an authorized patient relationship (PRD §11).
    if not has_active_care_relationship(db, patient_id=body.patient_id, doctor_id=user.id):
        raise APIError(403, "FORBIDDEN", "No active care relationship")
    if body.record_id is not None:
        record = db.get(MedicalRecords, body.record_id)
        if record is None or record.patient_id != body.patient_id:
            raise APIError(404, "NOT_FOUND")
    rx = Prescriptions(patient_id=body.patient_id, doctor_id=user.id,
                       record_id=body.record_id, medication=body.medication,
                       dosage=body.dosage, instructions=body.instructions)
    db.add(rx)
    db.flush()
    db.add(Notifications(user_id=body.patient_id, type="PRESCRIPTION_ISSUED",
                         title="A prescription was issued",
                         message="Open Prescriptions to review it."))
    audit(db, actor_id=user.id, role=user.role, event_type="PRESCRIPTION_CREATE",
          target_type="PRESCRIPTION", target_id=rx.id, outcome="SUCCESS")
    db.commit()
    db.refresh(rx)
    return {"id": rx.id, "patient_id": rx.patient_id, "doctor_id": rx.doctor_id,
            "medication": rx.medication, "issued_at": rx.issued_at.isoformat()}


@router.get("/prescriptions")
def list_prescriptions(user: Users = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> list:
    if user.role == ROLE_PATIENT:
        rows = db.execute(select(Prescriptions).where(
            Prescriptions.patient_id == user.id)).scalars().all()
    elif user.role == ROLE_DOCTOR:
        rows = db.execute(select(Prescriptions).where(
            Prescriptions.doctor_id == user.id)).scalars().all()
    else:
        raise APIError(403, "FORBIDDEN")
    return [{"id": r.id, "patient_id": r.patient_id, "doctor_id": r.doctor_id,
             "medication": r.medication, "dosage": r.dosage, "instructions": r.instructions,
             "issued_at": r.issued_at.isoformat()} for r in rows]


# ---------- Access history (role-scoped; denials included) ----------

@router.get("/access-history")
def access_history(user: Users = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> list:
    if user.role == ROLE_PATIENT:
        rows = db.execute(select(AccessLogs).where(
            AccessLogs.resource_type.in_(["RECORD", "MEDICAL_FILE"]),
            AccessLogs.resource_id.in_(
                select(MedicalRecords.id).where(MedicalRecords.patient_id == user.id)
            ),
        ).order_by(AccessLogs.created_at.desc())).scalars().all()
    else:
        rows = db.execute(select(AccessLogs).where(
            AccessLogs.actor_id == user.id).order_by(
            AccessLogs.created_at.desc())).scalars().all()
    return [{"id": a.id, "actor_id": a.actor_id, "role": a.role, "action": a.action,
             "resource_type": a.resource_type, "resource_id": a.resource_id,
             "outcome": a.outcome, "created_at": a.created_at.isoformat()} for a in rows]


# ---------- Admin ----------

class StatusBody(BaseModel):
    status: str


@router.patch("/admin/users/{user_id}/status")
def set_user_status(user_id: int, body: StatusBody,
                    admin: Users = Depends(require_system_admin),
                    db: Session = Depends(get_db)) -> dict:
    if user_id == admin.id:
        # Self-role/status change blocked (AppFlow §14).
        raise APIError(409, "CONFLICT", "Self status change is blocked")
    if body.status not in ACCOUNT_STATUSES:
        raise APIError(400, "VALIDATION_ERROR")
    target = db.get(Users, user_id)
    if target is None or target.status == "DELETED":
        raise APIError(404, "NOT_FOUND")
    target.status = body.status
    audit(db, actor_id=admin.id, role=admin.role, event_type="ADMIN_USER_STATUS",
          target_type="USER", target_id=user_id, outcome="SUCCESS",
          details={"new_status": body.status})
    db.commit()
    return {"id": target.id, "status": target.status}


# ---------- Health ----------

@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    from ...core.config import settings as s
    db_ok = True
    try:
        db.execute(select(Users.id).limit(1))
    except Exception:
        db_ok = False
    import os
    storage_ok = os.path.isdir(s.STORAGE_ROOT)
    return {"status": "ok" if db_ok and storage_ok else "degraded",
            "checks": {"database": db_ok, "protected_storage": storage_ok,
                       "scan_mode": s.SECURITY_SCAN_MODE}}
