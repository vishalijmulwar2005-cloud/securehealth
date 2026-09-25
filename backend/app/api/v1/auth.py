"""Auth & session workflow (AppFlow §3; TRD §7): register/login/refresh/
logout/me. Failures audited and non-revealing; auth endpoints rate-limited
10/min/IP by the middleware; refresh rotates and revokes (TRD §7 Logout)."""
import datetime as dt

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.errors import APIError
from ...core.security import (
    ROLE_DOCTOR, ROLE_PATIENT, SELF_REGISTRABLE_ROLES,
    create_access_token, create_refresh_token, decode_token, hash_password,
    patient_pseudo_id, verify_password,
)
from ...db.session import get_db
from ...models.models import DoctorProfiles, PatientProfiles, Users
from ..deps import get_current_user, issue_session, revoke_jti
from ...services.audit import audit, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = ROLE_PATIENT
    hospital_id: int | None = None
    specialty: str | None = Field(default=None, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


def _session_payload(db: Session, user: Users) -> dict:
    access, access_jti = create_access_token(user.id, user.role)
    refresh, refresh_jti = create_refresh_token(user.id, user.role)
    now = utcnow()
    issue_session(db, user, access, access_jti, "access",
                  now + dt.timedelta(minutes=settings.ACCESS_TOKEN_MINUTES))
    issue_session(db, user, refresh, refresh_jti, "refresh",
                  now + dt.timedelta(days=settings.REFRESH_TOKEN_DAYS))
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_MINUTES * 60,
    }


@router.post("/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)) -> dict:
    if body.role not in SELF_REGISTRABLE_ROLES:
        # Privilege-escalation guard: admin/regulator roles are never self-registrable.
        raise APIError(403, "FORBIDDEN")
    exists = db.execute(select(Users.id).where(Users.email == body.email.lower())).scalar_one_or_none()
    if exists is not None:
        raise APIError(409, "CONFLICT")
    user = Users(email=body.email.lower(), password_hash=hash_password(body.password),
                 full_name=body.full_name, role=body.role,
                 hospital_id=body.hospital_id, status="ACTIVE")
    db.add(user)
    db.flush()
    if body.role == ROLE_PATIENT:
        db.add(PatientProfiles(user_id=user.id, pseudo_id=patient_pseudo_id(user.id)))
    elif body.role == ROLE_DOCTOR:
        db.add(DoctorProfiles(user_id=user.id, hospital_id=body.hospital_id,
                              specialty=body.specialty))
    payload = _session_payload(db, user)
    audit(db, actor_id=user.id, role=user.role, event_type="AUTH_REGISTER", outcome="SUCCESS")
    db.commit()
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name,
                     "role": user.role, "status": user.status}, **payload}


@router.post("/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)) -> dict:
    user = db.execute(select(Users).where(Users.email == body.email.lower())).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        # Safe non-revealing failure; the attempt is audited (Security & DB §3).
        audit(db, actor_id=user.id if user else None, role=user.role if user else None,
              event_type="AUTH_LOGIN", outcome="DENIED", details={"reason": "invalid_credentials"})
        db.commit()
        raise APIError(401, "UNAUTHORIZED")
    if user.status != "ACTIVE":
        audit(db, actor_id=user.id, role=user.role, event_type="AUTH_LOGIN", outcome="DENIED",
              details={"reason": "account_not_active"})
        db.commit()
        raise APIError(401, "UNAUTHORIZED")
    payload = _session_payload(db, user)
    audit(db, actor_id=user.id, role=user.role, event_type="AUTH_LOGIN", outcome="SUCCESS")
    db.commit()
    return payload


@router.post("/refresh")
def refresh(body: RefreshBody, db: Session = Depends(get_db)) -> dict:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except Exception:
        raise APIError(401, "UNAUTHORIZED")
    user = db.get(Users, int(payload["sub"]))
    if user is None or user.status != "ACTIVE":
        raise APIError(401, "UNAUTHORIZED")
    if not revoke_jti(db, payload["jti"]):
        # Replayed/unknown/already-rotated refresh token.
        audit(db, actor_id=user.id, role=user.role, event_type="AUTH_REFRESH", outcome="DENIED",
              details={"reason": "unknown_or_rotated_token"})
        db.commit()
        raise APIError(401, "UNAUTHORIZED")
    new = _session_payload(db, user)
    audit(db, actor_id=user.id, role=user.role, event_type="AUTH_REFRESH", outcome="SUCCESS")
    db.commit()
    return new


@router.post("/logout")
def logout(body: RefreshBody, db: Session = Depends(get_db)) -> dict:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except Exception:
        raise APIError(401, "UNAUTHORIZED")
    revoke_jti(db, payload["jti"])
    audit(db, actor_id=int(payload["sub"]), role=payload.get("role"),
          event_type="AUTH_LOGOUT", outcome="SUCCESS")
    db.commit()
    return {"status": "logged_out"}


@router.get("/me")
def me(user: Users = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    data = {"id": user.id, "email": user.email, "full_name": user.full_name,
            "role": user.role, "status": user.status, "hospital_id": user.hospital_id}
    if user.role == ROLE_PATIENT:
        profile = db.execute(select(PatientProfiles).where(
            PatientProfiles.user_id == user.id)).scalar_one_or_none()
        if profile:
            data["pseudo_id"] = profile.pseudo_id
    return data
