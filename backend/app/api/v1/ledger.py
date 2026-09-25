"""Ledger API (TRD §17; Implementation Plan Phase 11).

Read endpoints are open to any authenticated role (regulator verification is
read-only); tamper/restore demos are SYSTEM_ADMIN-only and always audited.
The UI never shows CONFIRMED state that the ledger cannot substantiate.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...models.models import LedgerBlocks, Users
from ..deps import get_current_user, require_system_admin
from ...services import ledger as ledger_svc
from ...services.audit import audit

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("/blocks")
def list_blocks(type: str | None = Query(default=None), limit: int = Query(default=50, le=200),
                db: Session = Depends(get_db)) -> dict:
    ledger_svc.ensure_genesis(db)
    db.commit()
    q = select(LedgerBlocks).order_by(LedgerBlocks.block_index.desc()).limit(limit)
    if type:
        q = q.where(LedgerBlocks.type == type)
    rows = db.execute(q).scalars().all()
    types = {}
    for b in db.execute(select(LedgerBlocks.type)).scalars().all():
        types[b] = types.get(b, 0) + 1
    return {
        "total": sum(types.values()), "types": types,
        "blocks": [{"index": b.block_index, "timestamp": b.timestamp.isoformat(),
                    "type": b.type, "data": b.data_json, "previous_hash": b.previous_hash,
                    "nonce": b.nonce, "hash": b.block_hash} for b in rows],
    }


@router.get("/verify")
def verify(db: Session = Depends(get_db)) -> dict:
    result = ledger_svc.validate_chain(db)
    return {"valid": result["valid"], "broken_index": result["broken_index"],
            "count": result["count"]}


class TamperBody(BaseModel):
    patch: dict = Field(default_factory=lambda: {"note": "authorized tamper demo"})


@router.post("/tamper/{index}")
def tamper(index: int, body: TamperBody, admin: Users = Depends(require_system_admin),
           db: Session = Depends(get_db)) -> dict:
    row = ledger_svc.tamper_block(db, index, body.patch)
    if row is None:
        from ...core.errors import APIError
        raise APIError(404, "NOT_FOUND")
    audit(db, actor_id=admin.id, role=admin.role, event_type="LEDGER_TAMPER_DEMO",
          target_type="LEDGER_BLOCK", target_id=row.id, outcome="SUCCESS",
          details={"index": index})
    db.commit()
    validation = ledger_svc.validate_chain(db)
    return {"tampered_index": index, "validation": validation}


@router.post("/restore/{index}")
def restore(index: int, admin: Users = Depends(require_system_admin),
            db: Session = Depends(get_db)) -> dict:
    restored = ledger_svc.restore_block(db, index)
    if restored is None:
        from ...core.errors import APIError
        raise APIError(404, "NOT_FOUND")
    audit(db, actor_id=admin.id, role=admin.role, event_type="LEDGER_RESTORE",
          target_type="LEDGER_BLOCK", target_id=index, outcome="SUCCESS")
    db.commit()
    validation = ledger_svc.validate_chain(db)
    return {"restored_index": index, "restore_block": restored.block_index,
            "validation": validation}
