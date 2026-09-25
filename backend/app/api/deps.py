"""Shared dependencies: DB session, authenticated identity, role guards.

Identity always re-resolves role/account state from the DB (TRD §7: client
role claims are never trusted). Suspended/disabled/deleted accounts are denied.
"""
import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import APIError
from ..core.security import ROLE_SYSTEM_ADMIN, decode_token
from ..db.session import get_db
from ..models.models import AuthSessions, Users


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Users:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise APIError(401, "UNAUTHORIZED")
    try:
        payload = decode_token(auth[7:], expected_type="access")
    except jwt.PyJWTError:
        raise APIError(401, "UNAUTHORIZED")
    user = db.get(Users, int(payload["sub"]))
    if user is None or user.status != "ACTIVE":
        # Suspended/disabled/deleted accounts cannot use protected token state.
        raise APIError(401, "UNAUTHORIZED")
    request.state.user = user
    return user


def require_system_admin(user: Users = Depends(get_current_user)) -> Users:
    if user.role != ROLE_SYSTEM_ADMIN:
        raise APIError(403, "FORBIDDEN")
    return user


def issue_session(db: Session, user: Users, token: str, jti: str, token_type: str,
                  expires_at) -> None:
    db.add(AuthSessions(user_id=user.id, jti=jti, token_type=token_type,
                        expires_at=expires_at))


def revoke_jti(db: Session, jti: str) -> bool:
    row = db.execute(select(AuthSessions).where(AuthSessions.jti == jti,
                                                AuthSessions.revoked_at.is_(None))).scalar_one_or_none()
    if row is None:
        return False
    from ..services.audit import utcnow
    row.revoked_at = utcnow()
    return True
