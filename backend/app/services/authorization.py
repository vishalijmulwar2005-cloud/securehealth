"""Centralized server-side authorization (TRD v4.1 §8; master prompt §8).

Canonical policy chain for every protected action:
  Authenticate -> Resolve Role (from DB) -> Resolve Resource ->
  Ownership/Relationship (care_relationships) -> Consent/Permission ->
  Time Window -> Resource State -> Execute/Deny -> Audit relevant outcome.

IDOR policy: a resource that does not exist (or that the caller has no
permission context for) resolves to a safe 404 so IDs cannot be enumerated; a
caller with a permission context that is revoked/expired/rejected receives a
controlled 403 (matches the E2E revoke-retry path). Denials are always audited.
"""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import APIError
from ..models.models import CareRelationships, MedicalRecords, Permissions, ResearchConsents, Users
from .audit import access_log, audit, utcnow

RESOURCE_RECORD_CONTAINER = "RECORD_CONTAINER"
RESOURCE_RECORD = "RECORD"


def _patient_profile_id(db: Session, user_id: int) -> int | None:
    from ..models.models import PatientProfiles
    row = db.execute(select(PatientProfiles).where(PatientProfiles.user_id == user_id)).scalar_one_or_none()
    return row.id if row else None


def effective_permission_status(perm: Permissions, now: dt.datetime | None = None) -> str:
    """Lazy expiry enforcement (TRD §9): an expired window reports EXPIRED and
    blocks the next protected retrieval even before any sweeper runs."""
    now = now or utcnow()
    if perm.status == "ACTIVE" and perm.expires_at is not None:
        expires = perm.expires_at if perm.expires_at.tzinfo else perm.expires_at.replace(tzinfo=dt.timezone.utc)
        if expires < now:
            return "EXPIRED"
    return perm.status


def _in_window(perm: Permissions, now: dt.datetime) -> bool:
    start = perm.start_at if perm.start_at is None or perm.start_at.tzinfo else perm.start_at.replace(tzinfo=dt.timezone.utc)
    if start is not None and start > now:
        return False
    return effective_permission_status(perm, now) == "ACTIVE"


def has_active_care_relationship(db: Session, *, patient_id: int, doctor_id: int) -> bool:
    row = db.execute(
        select(CareRelationships).where(
            CareRelationships.patient_id == patient_id,
            CareRelationships.doctor_id == doctor_id,
            CareRelationships.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    return row is not None


def has_active_research_consent(db: Session, *, patient_id: int) -> bool:
    """Authoritative gate for local FL participation (research_consents only)."""
    row = db.execute(
        select(ResearchConsents).where(
            ResearchConsents.patient_id == patient_id,
            ResearchConsents.status == "ACTIVE",
        )
    ).scalars().first()
    if row is None:
        return False
    now = utcnow()
    if row.expires_at is not None:
        exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=dt.timezone.utc)
        if exp < now:
            return False
    if row.start_at is not None:
        start = row.start_at if row.start_at.tzinfo else row.start_at.replace(tzinfo=dt.timezone.utc)
        if start > now:
            return False
    return True


def _deny(db: Session, user: Users, action: str, resource_type: str, resource_id: int | None,
          status: int, code: str, reason: str) -> None:
    """Audit the denial, commit it, then raise the controlled error."""
    audit(db, actor_id=user.id if user else None, role=user.role if user else None,
          event_type=f"{action}.DENIED", target_type=resource_type, target_id=resource_id,
          outcome="DENIED", details={"reason": reason})
    access_log(db, actor_id=user.id if user else None, role=user.role if user else None,
               action=action, resource_type=resource_type, resource_id=resource_id,
               outcome="DENIED", details={"reason": reason})
    db.commit()
    raise APIError(status, code)


def authorize_record_access(db: Session, user: Users, record_id: int,
                            action: str = "RECORD_ACCESS") -> "MedicalRecords":
    """Resolve a medical record for the caller under the canonical chain."""
    now = utcnow()
    record = db.get(MedicalRecords, record_id)
    if record is None or record.status == "DELETED":
        # Safe not-found: no existence disclosure (TRD §14 NOT_FOUND).
        _deny(db, user, action, RESOURCE_RECORD, record_id, 404, "NOT_FOUND",
              "missing_or_deleted")
    from ..core.config import settings

    if user.role == "PATIENT":
        if _patient_profile_id(db, user.id) is None or record.patient_id != user.id:
            _deny(db, user, action, RESOURCE_RECORD, record_id, 404, "NOT_FOUND",
                  "not_owner")
        return record

    if user.role == "DOCTOR":
        perms = db.execute(
            select(Permissions).where(
                Permissions.recipient_user_id == user.id,
                Permissions.patient_id == record.patient_id,
                Permissions.resource_type.in_([RESOURCE_RECORD, RESOURCE_RECORD_CONTAINER]),
            )
        ).scalars().all()
        record_scoped = [p for p in perms if p.resource_id in (None, record_id)]
        if not record_scoped:
            # Doctor guessing an ID with no permission context -> hidden (IDOR).
            _deny(db, user, action, RESOURCE_RECORD, record_id, 404, "NOT_FOUND",
                  "no_permission_context")

        active = [p for p in record_scoped if _in_window(p, now)]
        if not active:
            # Caller had/has permission context that is PENDING/REVOKED/EXPIRED/REJECTED.
            _deny(db, user, action, RESOURCE_RECORD, record_id, 403, "FORBIDDEN",
                  "permission_not_active")

        if settings.REQUIRE_CARE_RELATIONSHIP and not has_active_care_relationship(
            db, patient_id=record.patient_id, doctor_id=user.id
        ):
            _deny(db, user, action, RESOURCE_RECORD, record_id, 403, "FORBIDDEN",
                  "no_active_care_relationship")
        return record

    # Admin/regulator roles never get automatic clinical access.
    _deny(db, user, action, RESOURCE_RECORD, record_id, 403, "FORBIDDEN",
          "role_not_clinically_authorized")
