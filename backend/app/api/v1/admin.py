"""System-admin operations: user directory, account lifecycle, and
institutional care-relationship binding (AppFlow §14 user management;
`care_relationships` are the authoritative doctor-patient access binding).
All actions are audited; self status/role change is blocked."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import APIError
from ...db.session import get_db
from ...models.models import CareRelationships, Users
from ..deps import require_system_admin
from ...services.audit import audit, utcnow

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(admin: Users = Depends(require_system_admin),
               db: Session = Depends(get_db)) -> list:
    rows = db.execute(select(Users).order_by(Users.id)).scalars().all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
             "status": u.status, "hospital_id": u.hospital_id} for u in rows]


class RelationshipBody(BaseModel):
    patient_id: int
    doctor_id: int
    hospital_id: int | None = None
    relationship_type: str = Field(default="PRIMARY_CARE", max_length=64)


@router.post("/care-relationships", status_code=201)
def bind_care_relationship(body: RelationshipBody,
                           admin: Users = Depends(require_system_admin),
                           db: Session = Depends(get_db)) -> dict:
    """Institutional binding: a doctor role alone never grants access; this
    authorized administrative operation creates the relationship that policy
    then requires for doctor access."""
    patient = db.get(Users, body.patient_id)
    doctor = db.get(Users, body.doctor_id)
    if patient is None or patient.role != "PATIENT":
        raise APIError(404, "NOT_FOUND", "Patient not found")
    if doctor is None or doctor.role != "DOCTOR":
        raise APIError(404, "NOT_FOUND", "Doctor not found")
    existing = db.execute(select(CareRelationships).where(
        CareRelationships.patient_id == body.patient_id,
        CareRelationships.doctor_id == body.doctor_id,
        CareRelationships.status == "ACTIVE")).scalar_one_or_none()
    if existing is not None:
        raise APIError(409, "CONFLICT")
    row = CareRelationships(patient_id=body.patient_id, doctor_id=body.doctor_id,
                            hospital_id=body.hospital_id or doctor.hospital_id,
                            relationship_type=body.relationship_type, status="ACTIVE")
    db.add(row)
    audit(db, actor_id=admin.id, role=admin.role, event_type="CARE_RELATIONSHIP_BIND",
          target_type="CARE_RELATIONSHIP", target_id=row.id, outcome="SUCCESS",
          details={"patient_id": body.patient_id, "doctor_id": body.doctor_id})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "patient_id": row.patient_id, "doctor_id": row.doctor_id,
            "status": row.status, "start_at": row.start_at.isoformat()}


@router.post("/care-relationships/{relationship_id}/end")
def end_care_relationship(relationship_id: int,
                          admin: Users = Depends(require_system_admin),
                          db: Session = Depends(get_db)) -> dict:
    row = db.get(CareRelationships, relationship_id)
    if row is None or row.status != "ACTIVE":
        raise APIError(404, "NOT_FOUND")
    row.status = "ENDED"
    row.end_at = utcnow()
    row.ended_at = utcnow()
    audit(db, actor_id=admin.id, role=admin.role, event_type="CARE_RELATIONSHIP_END",
          target_type="CARE_RELATIONSHIP", target_id=row.id, outcome="SUCCESS")
    db.commit()
    return {"id": row.id, "status": row.status}


class HospitalStatusBody(BaseModel):
    active: bool


@router.patch("/hospitals/{hospital_id}/status")
def set_hospital_status(hospital_id: int, body: HospitalStatusBody,
                        admin: Users = Depends(require_system_admin),
                        db: Session = Depends(get_db)) -> dict:
    """Pause/resume a consortium node (AppFlow §14 node operations)."""
    from ...models.models import Hospitals
    from ...services.ledger_outbox import enqueue
    hospital = db.get(Hospitals, hospital_id)
    if hospital is None:
        raise APIError(404, "NOT_FOUND")
    hospital.active = body.active
    event_type = "NODE_RESUMED" if body.active else "NODE_PAUSED"
    audit_row = audit(db, actor_id=admin.id, role=admin.role, event_type=event_type,
                      target_type="HOSPITAL", target_id=hospital.id, outcome="SUCCESS")
    enqueue(db, event_type="NODE_" + ("RESUMED" if body.active else "PAUSED"),
            ref=hospital.code, audit_event_id=audit_row.id,
            data={"hospital": hospital.code, "active": body.active})
    db.commit()
    return {"id": hospital.id, "code": hospital.code, "active": hospital.active}


@router.get("/audit")
def filtered_audit(action: str | None = None, outcome: str | None = None,
                   limit: int = 100, admin: Users = Depends(require_system_admin),
                   db: Session = Depends(get_db)) -> list:
    from ...models.models import AuditLogs as AL
    q = select(AL).order_by(AL.id.desc()).limit(min(limit, 300))
    if action:
        q = q.where(AL.event_type == action)
    if outcome:
        q = q.where(AL.outcome == outcome)
    rows = db.execute(q).scalars().all()
    return [{"id": a.id, "actor_id": a.actor_id, "role": a.role,
             "event_type": a.event_type, "target_type": a.target_type,
             "target_id": a.target_id, "outcome": a.outcome,
             "created_at": a.created_at.isoformat(),
             "block_ref": a.block_ref} for a in rows]
