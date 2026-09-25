"""Password hashing, JWT session tokens and pseudonymous identifiers.

TRD v4.1 §7: HS256, claims sub/role/type/iat/exp/jti, 30-min access target,
7-day refresh target, bcrypt passwords, DB role resolution (client claims never
trusted), HMAC-SHA-256 pseudonymous patient IDs (Security & Database §7).
"""
import datetime as dt
import hmac
import hashlib
import uuid

import bcrypt
import jwt

from .config import settings

ROLE_PATIENT = "PATIENT"
ROLE_DOCTOR = "DOCTOR"
ROLE_HOSPITAL_ADMIN = "HOSPITAL_ADMIN"
ROLE_SYSTEM_ADMIN = "SYSTEM_ADMIN"
ROLE_REGULATOR = "REGULATOR"

SELF_REGISTRABLE_ROLES = {ROLE_PATIENT, ROLE_DOCTOR}  # escalation guard: admin roles are never self-registrable


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def _encode(*, subject: int, role: str, token_type: str, lifetime: dt.timedelta) -> tuple[str, str]:
    now = dt.datetime.now(dt.timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(subject),
        "role": role,  # informational only; authorization always re-resolves from DB
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": jti,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), jti


def create_access_token(user_id: int, role: str) -> tuple[str, str]:
    return _encode(subject=user_id, role=role, token_type="access",
                   lifetime=dt.timedelta(minutes=settings.ACCESS_TOKEN_MINUTES))


def create_refresh_token(user_id: int, role: str) -> tuple[str, str]:
    return _encode(subject=user_id, role=role, token_type="refresh",
                   lifetime=dt.timedelta(days=settings.REFRESH_TOKEN_DAYS))


def decode_token(token: str, expected_type: str | None = None) -> dict:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def patient_pseudo_id(user_id: int) -> str:
    """HMAC-SHA-256 with a server-side secret (Security & Database §7).

    Plain SHA-256 of predictable identifiers is never used as a security identity.
    """
    digest = hmac.new(settings.PSEUDO_SECRET.encode(), f"patient:{user_id}".encode(),
                      hashlib.sha256).hexdigest()
    return f"PT-{digest[:10].upper()}"
