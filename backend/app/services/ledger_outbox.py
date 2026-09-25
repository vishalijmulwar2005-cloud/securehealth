"""Ledger outbox + worker (master prompt §16; TRD v4.1 §18).

Domain transaction commits state + audit + durable outbox reference; the
worker mines the PoW event ASYNCHRONOUSLY and only then marks it CONFIRMED.
No path may report CONFIRMED before the block exists. The in-process worker
is the documented dev/test implementation; production runs the same outbox on
the durable queue (Celery, Phase 8/12).

The event type travels in tx_reference ("TYPE:ref") and becomes the block
type — the on-chain payload stays metadata-only.
"""
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.session import SessionLocal
from ..models.models import BlockchainEvents
from . import ledger

_lock = threading.Lock()


def enqueue(db: Session, *, event_type: str, data: dict, ref: str | int | None = None,
            audit_event_id: int | None = None) -> BlockchainEvents:
    """Durable outbox reference — commits with the caller's domain transaction.
    audit_event_id links the event to its audit row so the worker can stamp the
    mined block index back onto it (ledger-linked auditability)."""
    row = BlockchainEvents(
        tx_reference=f"{event_type}:{ref}" if ref is not None else event_type,
        audit_event_id=audit_event_id,
        state="QUEUED", data_json=data,
    )
    db.add(row)
    db.flush()
    return row


def process_outbox(db: Session, *, limit: int = 100) -> int:
    """Mine all pending outbox events in order; QUEUED → SUBMITTED → CONFIRMED."""
    with _lock:
        processed = 0
        rows = db.execute(select(BlockchainEvents).where(
            BlockchainEvents.state == "QUEUED").order_by(BlockchainEvents.id)).scalars().all()
        for event in rows[:limit]:
            event.state = "SUBMITTED"
            db.commit()  # claim is durable before mining starts
            try:
                btype = (event.tx_reference or "NODE_EVENT").split(":", 1)[0]
                block = ledger.mine_block(db, btype=btype, data=event.data_json or {})
                event.block_id = block.id
                event.state = "CONFIRMED"
                if event.audit_event_id is not None:
                    from ..models.models import AuditLogs
                    audit_row = db.get(AuditLogs, event.audit_event_id)
                    if audit_row is not None:
                        # Ledger-linked auditability: stamp the mined block index.
                        audit_row.block_ref = str(block.block_index)
                db.commit()
                processed += 1
            except Exception:
                db.rollback()
                event.state = "FAILED"
                db.commit()
        return processed


_worker_started = False


def start_worker() -> None:
    """Background worker thread (dev/test). Production: durable queue worker."""
    global _worker_started
    if _worker_started:
        return
    _worker_started = True

    def loop() -> None:
        import time
        while True:
            db = SessionLocal()
            try:
                process_outbox(db)
            except Exception:
                db.rollback()
            finally:
                # End the read transaction every pass - otherwise the worker
                # stays pinned to a stale snapshot and never sees new events.
                db.rollback()
                db.close()
            time.sleep(0.5)

    threading.Thread(target=loop, name="ledger-worker", daemon=True).start()
