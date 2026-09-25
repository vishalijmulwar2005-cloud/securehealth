"""Audit & access logging (Security & Database §9).

Both relevant successes AND denials are recorded; denials never leak protected
metadata; no secrets or raw medical payloads go into logs.
"""
import datetime as dt

from sqlalchemy.orm import Session

from ..models.models import AccessLogs, AuditLogs


def audit(db: Session, *, actor_id: int | None, role: str | None, event_type: str,
          target_type: str | None = None, target_id: int | None = None,
          outcome: str = "SUCCESS", details: dict | None = None) -> AuditLogs:
    row = AuditLogs(actor_id=actor_id, role=role, event_type=event_type,
                    target_type=target_type, target_id=target_id, outcome=outcome,
                    details=_safe(details))
    db.add(row)
    db.flush()
    return row


def access_log(db: Session, *, actor_id: int | None, role: str | None, action: str,
               resource_type: str | None = None, resource_id: int | None = None,
               outcome: str = "GRANTED", details: dict | None = None) -> AccessLogs:
    row = AccessLogs(actor_id=actor_id, role=role, action=action,
                     resource_type=resource_type, resource_id=resource_id,
                     outcome=outcome, details=_safe(details))
    db.add(row)
    db.flush()
    return row


def _safe(details: dict | None) -> dict | None:
    """Redact anything that looks like a credential/secret; keep categories only."""
    if not details:
        return details
    redacted = {}
    for key, value in details.items():
        lk = key.lower()
        if any(t in lk for t in ("password", "token", "secret", "key")):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
