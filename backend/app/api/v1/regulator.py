"""Regulator read-only verification API (TRD §8 REGULATOR; AppFlow §15).

Read-only: chain/model integrity and audit chronology. No clinical content,
no mutation, no protected details — verification data only.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...models.models import AuditLogs, FederatedJobs, Users
from ..deps import get_current_user
from ...services import ledger as ledger_svc

router = APIRouter(prefix="/regulator", tags=["regulator"])


@router.get("/integrity")
def integrity(user: Users = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    validation = ledger_svc.validate_chain(db)
    jobs = db.execute(select(FederatedJobs).order_by(
        FederatedJobs.id.desc()).limit(40)).scalars().all()
    models, seen = [], set()
    for j in jobs:  # latest job per disease
        if j.disease_model in seen:
            continue
        seen.add(j.disease_model)
        models.append({"disease": j.disease_model, "round": j.round,
                       "model_hash": j.model_hash,
                       "cumulative_epsilon": j.cumulative_epsilon,
                       "block_index": j.block_index})
    return {"chain": validation, "models": models}


@router.get("/audit")
def audit_trail(limit: int = Query(default=50, le=200),
                user: Users = Depends(get_current_user), db: Session = Depends(get_db)) -> list:
    rows = db.execute(select(AuditLogs).order_by(
        AuditLogs.id.desc()).limit(limit)).scalars().all()
    # Chronology + outcome only — details excluded (no clinical metadata).
    return [{"id": a.id, "event_type": a.event_type, "target_type": a.target_type,
             "outcome": a.outcome, "created_at": a.created_at.isoformat(),
             "block_ref": a.block_ref} for a in rows]
