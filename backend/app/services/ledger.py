"""Port of the verified console's PoW ledger (server/blockchain.js).

SHA-256 hash chain, difficulty 3, mined in-process. Payloads are METADATA
ONLY — fingerprints, decisions and references, never medical values.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.hashing import sha256_hex
from ..models.models import BlockchainEvents, LedgerBlocks

DIFFICULTY = 3
PREFIX = "0" * DIFFICULTY
GENESIS_PREV = "0" * 64
MAX_NONCE = 5_000_000

GENESIS_NOTE = "SecureHealth ledger start. Metadata only — never medical values."


def canonical_hash(*, index: int, timestamp_ms: int, btype: str, data_json: str,
                   previous_hash: str, nonce: int) -> str:
    """Exact port: sha256Hex([index, timestamp, type, JSON.stringify(data), previousHash, nonce].join('|'))"""
    return sha256_hex("|".join([str(index), str(timestamp_ms), btype, data_json,
                                previous_hash, str(nonce)]))


def _stringify(data) -> str:
    """JS JSON.stringify equivalent for our ASCII payloads (compact, key order)."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def mine_block(db: Session, *, btype: str, data: dict,
               timestamp_ms: int | None = None) -> LedgerBlocks:
    """Mine and persist the next block on the chain (creating GENESIS if empty)."""
    ensure_genesis(db)
    prev = db.execute(select(LedgerBlocks).order_by(LedgerBlocks.block_index.desc())).scalars().first()
    index = (prev.block_index + 1) if prev else 0
    previous_hash = prev.block_hash if prev else GENESIS_PREV
    ts_ms = timestamp_ms if timestamp_ms is not None else int(__import__("time").time() * 1000)
    data_json = _stringify(data)
    nonce = 0
    b_hash = ""
    while nonce < MAX_NONCE:
        b_hash = canonical_hash(index=index, timestamp_ms=ts_ms, btype=btype,
                                data_json=data_json, previous_hash=previous_hash, nonce=nonce)
        if b_hash.startswith(PREFIX):
            break
        nonce += 1
    if not b_hash.startswith(PREFIX):
        raise RuntimeError("mining failed to converge")
    import datetime as dt
    row = LedgerBlocks(
        block_index=index,
        timestamp=dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc),
        timestamp_ms=ts_ms,
        type=btype, data_json=data, previous_hash=previous_hash,
        nonce=nonce, block_hash=b_hash,
    )
    db.add(row)
    db.flush()
    return row


def ensure_genesis(db: Session) -> None:
    exists = db.execute(select(LedgerBlocks.id).limit(1)).scalar_one_or_none()
    if exists is not None:
        return
    ts_ms = int(__import__("time").time() * 1000)
    data_json = _stringify({"note": GENESIS_NOTE})
    nonce = 0
    while nonce < MAX_NONCE:
        h = canonical_hash(index=0, timestamp_ms=ts_ms, btype="GENESIS",
                           data_json=data_json, previous_hash=GENESIS_PREV, nonce=nonce)
        if h.startswith(PREFIX):
            break
        nonce += 1
    import datetime as dt
    db.add(LedgerBlocks(
        block_index=0, timestamp=dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc),
        timestamp_ms=ts_ms,
        type="GENESIS", data_json={"note": GENESIS_NOTE}, previous_hash=GENESIS_PREV,
        nonce=nonce, block_hash=h,
    ))
    db.flush()


def _block_timestamp_ms(row: LedgerBlocks) -> int:
    return row.timestamp_ms  # exact mining time used in the canonical hash


def validate_chain(db: Session) -> dict:
    """Recompute every hash + link; report the exact broken block."""
    rows = db.execute(select(LedgerBlocks).order_by(LedgerBlocks.block_index)).scalars().all()
    for i, b in enumerate(rows):
        recomputed = canonical_hash(
            index=b.block_index, timestamp_ms=_block_timestamp_ms(b), btype=b.type,
            data_json=_stringify(b.data_json), previous_hash=b.previous_hash, nonce=b.nonce,
        )
        if recomputed != b.block_hash:
            return {"valid": False, "broken_index": b.block_index, "count": len(rows)}
        expected_prev = GENESIS_PREV if i == 0 else rows[i - 1].block_hash
        if b.previous_hash != expected_prev:
            return {"valid": False, "broken_index": b.block_index, "count": len(rows)}
    return {"valid": True, "broken_index": -1, "count": len(rows)}


def tamper_block(db: Session, index: int, patch: dict) -> LedgerBlocks | None:
    """Authorized demo: edit stored data WITHOUT re-mining → stored hash mismatches."""
    row = db.execute(select(LedgerBlocks).where(LedgerBlocks.block_index == index)).scalar_one_or_none()
    if row is None:
        return None
    merged = dict(row.data_json or {})
    merged.update(patch)
    merged["_tampered"] = True
    row.data_json = merged
    db.flush()
    return row


def restore_block(db: Session, index: int) -> LedgerBlocks | None:
    """Re-mine the edited block AND every block after it (links would otherwise
    stay broken), then append a RESTORE block. Chain whole again."""
    rows = db.execute(select(LedgerBlocks).order_by(LedgerBlocks.block_index)).scalars().all()
    target = None
    for r in rows:
        if r.block_index == index:
            target = r
            break
    if target is None:
        return None
    start = rows.index(target)
    for i in range(start, len(rows)):
        b = rows[i]
        b.previous_hash = GENESIS_PREV if i == 0 else rows[i - 1].block_hash
        ts_ms = _block_timestamp_ms(b)
        data_json = _stringify(b.data_json)
        nonce = 0
        while nonce < MAX_NONCE:
            h = canonical_hash(index=b.block_index, timestamp_ms=ts_ms, btype=b.type,
                               data_json=data_json, previous_hash=b.previous_hash, nonce=nonce)
            if h.startswith(PREFIX):
                b.nonce = nonce  # re-mined nonce must be stored, not just used
                b.block_hash = h
                break
            nonce += 1
    db.flush()
    return mine_block(db, btype="RESTORE", data={"index": index, "note": "BLOCK_RESTORED"})


def latest_block(db: Session) -> LedgerBlocks | None:
    return db.execute(select(LedgerBlocks).order_by(LedgerBlocks.block_index.desc())).scalars().first()


def served_model_matches(db: Session, *, disease: str, fingerprint: str) -> bool:
    """Served-model integrity: fingerprint must match the authoritative latest
    AGGREGATION block for that disease before being presented as ledger-verified."""
    rows = db.execute(select(BlockchainEvents).where(
        BlockchainEvents.state == "CONFIRMED")).scalars().all()
    block_ids = [e.block_id for e in rows if e.block_id]
    if not block_ids:
        return False
    blocks = db.execute(select(LedgerBlocks).where(
        LedgerBlocks.id.in_(block_ids)).order_by(LedgerBlocks.block_index.desc())).scalars().all()
    for b in blocks:
        if b.type == "AGGREGATION" and (b.data_json or {}).get("disease") == disease:
            return (b.data_json or {}).get("model_hash") == fingerprint
    return False
