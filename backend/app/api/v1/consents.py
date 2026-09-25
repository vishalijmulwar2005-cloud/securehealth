"""Consent, permission and research-consent workflows (TRD §9; AppFlow §7).

State machine: PENDING -> ACTIVE -> REVOKED/EXPIRED; PENDING -> REJECTED;
optional CANCELLED. Only the owning authenticated patient transitions
patient-controlled consent. Transitions are transactional + audited; both
parties are notified. Research consent (research_consents) is separate,
authoritative, and gates local FL participation.
"""
import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import APIError
from ...core.security import ROLE_DOCTOR, ROLE_PATIENT
from ...db.session import get_db
from ...models.models import (
    ALLOWED_PERMISSION_DURATIONS, ConsentRequests, Notifications, PatientProfiles,
    Permissions, ResearchConsents, Users,
)
from ..deps import get_current_user
from ...services.audit import audit, utcnow
from ...services.authorization import (
    RESOURCE_RECORD, RESOURCE_RECORD_CONTAINER, effective_permission_status,
)
from ...services.ledger_outbox import enqueue

router = APIRouter(tags=["consent"])


class RequestBody(BaseModel):
    patient_id: int
    resource_type: str = RESOURCE_RECORD_CONTAINER
    resource_id: int | None = None
    scope: str = Field(default="VIEW", max_length=64)
    purpose: str | None = Field(default=None, max_length=512)
    note: str | None = Field(default=None, max_length=512)


class DecisionBody(BaseModel):
    duration_days: int | None = None  # required on approve: 7/30/90
    reason: str | None = Field(default=None, max_length=512)


class RevokeBody(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class ResearchConsentBody(BaseModel):
    opt_in: bool
    scope: str | None = Field(default=None, max_length=255)
    allowed_organizations: list[int] | None = None
    duration_days: int | None = None


def _notify(db: Session, user_id: int, ntype: str, title: str, message: str) -> None:
    db.add(Notifications(user_id=user_id, type=ntype, title=title, message=message))


def _permission_payload(p: Permissions) -> dict:
    return {
        "id": p.id, "patient_id": p.patient_id, "recipient_user_id": p.recipient_user_id,
        "resource_type": p.resource_type, "resource_id": p.resource_id,
        "permission_type": p.permission_type, "status": effective_permission_status(p),
        "stored_status": p.status, "start_at": p.start_at.isoformat() if p.start_at else None,
        "expires_at": p.expires_at.isoformat() if p.expires_at else None,
        "granted_at": p.granted_at.isoformat() if p.granted_at else None,
        "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None,
    }


@router.post("/consents/requests", status_code=201)
def create_request(body: RequestBody, user: Users = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    if user.role != ROLE_DOCTOR:
        raise APIError(403, "FORBIDDEN")
    patient = db.get(Users, body.patient_id)
    if patient is None or patient.role != ROLE_PATIENT:
        raise APIError(404, "NOT_FOUND")
    if body.resource_type not in (RESOURCE_RECORD, RESOURCE_RECORD_CONTAINER):
        raise APIError(400, "VALIDATION_ERROR")
    if body.resource_type == RESOURCE_RECORD and body.resource_id is None:
        raise APIError(400, "VALIDATION_ERROR")
    req = ConsentRequests(patient_id=body.patient_id, requester_id=user.id,
                          resource_type=body.resource_type, resource_id=body.resource_id,
                          scope=body.scope, purpose=body.purpose, note=body.note,
                          status="PENDING")
    db.add(req)
    _notify(db, body.patient_id, "ACCESS_REQUEST",
            "A doctor requested access to selected records",
            "Open Privacy Center to review the request.")
    audit(db, actor_id=user.id, role=user.role, event_type="CONSENT_REQUEST",
          target_type=body.resource_type, target_id=body.resource_id, outcome="SUCCESS")
    db.commit()
    db.refresh(req)
    return {"id": req.id, "status": req.status, "patient_id": req.patient_id}


def _require_owning_patient(user: Users, patient_id: int) -> None:
    if user.role != ROLE_PATIENT or user.id != patient_id:
        # Only the owning authenticated patient may change care consent.
        raise APIError(403, "FORBIDDEN")


@router.post("/consents/requests/{request_id}/approve")
def approve_request(request_id: int, body: DecisionBody,
                    user: Users = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    req = db.get(ConsentRequests, request_id)
    if req is None or req.status != "PENDING":
        raise APIError(404, "NOT_FOUND")
    _require_owning_patient(user, req.patient_id)
    if body.duration_days not in ALLOWED_PERMISSION_DURATIONS:
        raise APIError(400, "VALIDATION_ERROR")
    now = utcnow()
    perm = Permissions(
        patient_id=req.patient_id, recipient_user_id=req.requester_id,
        resource_type=req.resource_type, resource_id=req.resource_id,
        permission_type=req.scope, status="ACTIVE",
        start_at=now, expires_at=now + dt.timedelta(days=body.duration_days),
        granted_at=now,
    )
    req.status = "APPROVED"
    db.add(perm)
    db.flush()
    perm.audit_ref = f"consent_request:{req.id}"
    _notify(db, req.requester_id, "PERMISSION_GRANTED",
            "Your selected permission is now active",
            f"Active for {body.duration_days} days.")
    # Transactional: request state + permission + notifications commit together.
    audit(db, actor_id=user.id, role=user.role, event_type="CONSENT_APPROVE",
          target_type="PERMISSION", target_id=perm.id, outcome="SUCCESS")
    db.commit()
    return _permission_payload(perm)


@router.post("/consents/requests/{request_id}/reject")
def reject_request(request_id: int, body: DecisionBody,
                   user: Users = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    req = db.get(ConsentRequests, request_id)
    if req is None or req.status != "PENDING":
        raise APIError(404, "NOT_FOUND")
    _require_owning_patient(user, req.patient_id)
    req.status = "REJECTED"
    _notify(db, req.requester_id, "PERMISSION_REJECTED",
            "Your access request was rejected",
            body.reason or "The patient declined this request.")
    audit(db, actor_id=user.id, role=user.role, event_type="CONSENT_REJECT",
          target_type="CONSENT_REQUEST", target_id=req.id, outcome="SUCCESS")
    db.commit()
    return {"id": req.id, "status": req.status}


@router.post("/permissions/{permission_id}/revoke")
def revoke_permission(permission_id: int, body: RevokeBody,
                      user: Users = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict:
    perm = db.get(Permissions, permission_id)
    if perm is None or effective_permission_status(perm) not in ("PENDING", "ACTIVE"):
        raise APIError(404, "NOT_FOUND")
    _require_owning_patient(user, perm.patient_id)
    now = utcnow()
    perm.status = "REVOKED"
    perm.revoked_at = now
    # Committed revoke immediately blocks subsequent retrieval (lazy checks).
    _notify(db, perm.recipient_user_id, "PERMISSION_REVOKED",
            "A previously active permission was revoked",
            body.reason or "Access has been revoked by the patient.")
    audit(db, actor_id=user.id, role=user.role, event_type="CONSENT_REVOKE",
          target_type="PERMISSION", target_id=perm.id, outcome="SUCCESS")
    db.commit()
    return _permission_payload(perm)


@router.get("/consents")
def list_consents(user: Users = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    if user.role == ROLE_PATIENT:
        perms = db.execute(select(Permissions).where(
            Permissions.patient_id == user.id)).scalars().all()
        reqs = db.execute(select(ConsentRequests).where(
            ConsentRequests.patient_id == user.id)).scalars().all()
    elif user.role == ROLE_DOCTOR:
        perms = db.execute(select(Permissions).where(
            Permissions.recipient_user_id == user.id)).scalars().all()
        reqs = db.execute(select(ConsentRequests).where(
            ConsentRequests.requester_id == user.id)).scalars().all()
    else:
        raise APIError(403, "FORBIDDEN")
    return {
        "permissions": [_permission_payload(p) for p in perms],
        "requests": [{"id": r.id, "patient_id": r.patient_id, "requester_id": r.requester_id,
                      "resource_type": r.resource_type, "resource_id": r.resource_id,
                      "scope": r.scope, "status": r.status} for r in reqs],
    }


@router.post("/research-consents", status_code=201)
def set_research_consent(body: ResearchConsentBody,
                         user: Users = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> dict:
    if user.role != ROLE_PATIENT:
        raise APIError(403, "FORBIDDEN")
    now = utcnow()
    row = db.execute(select(ResearchConsents).where(
        ResearchConsents.patient_id == user.id,
        ResearchConsents.status == "ACTIVE")).scalars().first()
    if body.opt_in:
        if row is not None:
            raise APIError(409, "CONFLICT")
        if body.duration_days is not None and body.duration_days not in ALLOWED_PERMISSION_DURATIONS:
            raise APIError(400, "VALIDATION_ERROR")
        row = ResearchConsents(
            patient_id=user.id, status="ACTIVE", scope=body.scope,
            allowed_organizations=body.allowed_organizations,
            start_at=now,
            expires_at=(now + dt.timedelta(days=body.duration_days))
            if body.duration_days else None,
        )
        db.add(row)
        db.flush()
        # patient_profiles cache is non-authoritative; refresh it best-effort.
        profile = db.execute(select(PatientProfiles).where(
            PatientProfiles.user_id == user.id)).scalar_one_or_none()
        if profile:
            profile.research_consent_cache = True
    else:
        if row is None:
            raise APIError(404, "NOT_FOUND")
        row.status = "REVOKED"
        row.revoked_at = now
        profile = db.execute(select(PatientProfiles).where(
            PatientProfiles.user_id == user.id)).scalar_one_or_none()
        if profile:
            profile.research_consent_cache = False
    audit_row = audit(db, actor_id=user.id, role=user.role, event_type="RESEARCH_CONSENT_CHANGE",
                      target_type="RESEARCH_CONSENT", target_id=row.id, outcome="SUCCESS",
                      details={"opt_in": body.opt_in})
    # CONSENT decision reference goes through the durable outbox (metadata only).
    enqueue(db, event_type="CONSENT", ref=f"research:{row.id}",
            audit_event_id=audit_row.id,
            data={"decision": "GRANTED" if body.opt_in else "REVOKED",
                  "scope": row.scope or "LOCAL_FL",
                  "patient_pseudo": f"research-consent:{row.id}"})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "expires_at":
            row.expires_at.isoformat() if row.expires_at else None}


@router.get("/research-consents/me")
def my_research_consent(user: Users = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> list:
    row = db.execute(select(ResearchConsents).where(
        ResearchConsents.patient_id == user.id)).scalars().all()
    return [{"id": r.id, "status": r.status, "scope": r.scope,
             "allowed_organizations": r.allowed_organizations,
             "expires_at": r.expires_at.isoformat() if r.expires_at else None}
            for r in row]
