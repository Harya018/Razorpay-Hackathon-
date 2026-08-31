import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

GENESIS_HASH = "0" * 64

# How many chains of tampered/broken history we're willing to scan through
# to find "the last row in this chain" — bounded so a write never does an
# unbounded table scan. Fine at hackathon scale; a real deployment would
# want a dedicated, indexed session_id column instead of parsing payload
# JSON to find chain membership.
_CHAIN_LOOKUP_WINDOW = 500


def chain_key_for_session(session_id: str) -> str:
    return f"session:{session_id}"


def _chain_key(order_id: Optional[int], payload: dict) -> str:
    session_id = payload.get("session_id")
    if session_id:
        return chain_key_for_session(session_id)
    if order_id is not None:
        return f"order:{order_id}"
    return "global"


def _entry_hash(previous_hash: str, event_type: str, payload_json: str, created_at: datetime) -> str:
    # SQLite round-trips DateTime columns as naive (drops tzinfo) — hash the
    # naive form on both the write path and the read-back verify path, or
    # the exact same row would hash differently before and after a reload.
    naive_iso = created_at.replace(tzinfo=None).isoformat()
    return hashlib.sha256(f"{previous_hash}|{event_type}|{payload_json}|{naive_iso}".encode("utf-8")).hexdigest()


def _previous_entry_hash(db: Session, chain_key: str) -> str:
    """Chains are per session_id (or per-order/global for non-negotiation
    events), not one single chain across the whole table — simpler to
    reason about for a hackathon, and sufficient to prove tamper-evidence
    within one negotiation's own story, which is what actually matters
    here. Documented choice, not an oversight.
    """
    candidates = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(_CHAIN_LOOKUP_WINDOW).all()
    for row in candidates:
        try:
            row_payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        if _chain_key(row.order_id, row_payload) == chain_key and row.entry_hash:
            return row.entry_hash
    return GENESIS_HASH


def find_active_chain_key(db: Session) -> Optional[str]:
    """The chain_key of the most recently written row that belongs to a
    real per-session/per-order chain (i.e. not the sandbox chain below) —
    "most recently active chain" for the dashboard's Audit Trail panel to
    default to. Skips the sandbox chain so a judge tampering with the
    sandbox never hides the real chain the panel would otherwise show.
    """
    candidates = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(_CHAIN_LOOKUP_WINDOW).all()
    for row in candidates:
        try:
            row_payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        key = _chain_key(row.order_id, row_payload)
        if key != SANDBOX_CHAIN_KEY:
            return key
    return None


def get_chain_entries(db: Session, chain_key: str, limit: int = 15) -> list[AuditLog]:
    """Every row belonging to one chain, oldest-first, last `limit` only —
    same bounded-scan tradeoff as _previous_entry_hash/verify_chain (see
    their own notes): fine at hackathon scale, would want an indexed
    chain_key column for a real deployment.
    """
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(_CHAIN_LOOKUP_WINDOW).all()
    chain_rows = []
    for row in rows:
        try:
            row_payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        if _chain_key(row.order_id, row_payload) == chain_key:
            chain_rows.append(row)
        if len(chain_rows) >= limit:
            break
    chain_rows.reverse()  # oldest first, matching verify_chain's own ordering
    return chain_rows


# --- sandbox chain: a dedicated, synthetic chain for the dashboard's ------
# "try breaking it" demo, so a judge can watch tamper detection fire live
# without any risk of touching a real negotiation/order's own audit trail.
SANDBOX_CHAIN_KEY = chain_key_for_session("demo:sandbox")
_SANDBOX_SESSION_ID = "demo:sandbox"
SANDBOX_SIZE = 4


def seed_sandbox_chain(db: Session) -> list[AuditLog]:
    """(Re)creates a small, clean sandbox chain — real write_audit_log
    calls, so these rows are hash-chained by the exact same code path as
    every genuine negotiation event; only the CONTENT is synthetic.
    """
    db.query(AuditLog).filter(AuditLog.event_type == "demo_sandbox_entry").delete()
    db.commit()
    notes = [
        "Sandbox opened",
        "Sandbox offer proposed",
        "Sandbox offer accepted",
        "Sandbox order recorded",
    ]
    for i, note in enumerate(notes[:SANDBOX_SIZE], start=1):
        write_audit_log(
            db,
            order_id=None,
            event_type="demo_sandbox_entry",
            payload={"session_id": _SANDBOX_SESSION_ID, "seq": i, "note": note},
        )
    return get_chain_entries(db, SANDBOX_CHAIN_KEY, limit=SANDBOX_SIZE)


def tamper_sandbox_chain(db: Session) -> Optional[AuditLog]:
    """Corrupts the OLDEST sandbox row's stored payload in place, without
    recomputing its entry_hash — a direct row UPDATE, deliberately
    bypassing write_audit_log, to simulate exactly what an attacker
    tampering with the database directly (not through the app) would do.
    Returns the tampered row, or None if the sandbox hasn't been seeded.
    """
    rows = get_chain_entries(db, SANDBOX_CHAIN_KEY, limit=SANDBOX_SIZE)
    if not rows:
        return None
    target = rows[0]
    try:
        payload = json.loads(target.payload) if target.payload else {}
    except (TypeError, json.JSONDecodeError):
        payload = {}
    payload["note"] = (payload.get("note") or "") + " [TAMPERED]"
    target.payload = json.dumps(payload, sort_keys=True)  # entry_hash intentionally left stale
    db.commit()
    return target


def write_audit_log(db: Session, order_id: Optional[int], event_type: str, payload: dict) -> AuditLog:
    """Single choke point for writing audit_log rows — every negotiation
    node and every checkout path goes through this, so hash-chaining lives
    in exactly one place.

    entry_hash = sha256(previous_hash | event_type | payload | created_at),
    where previous_hash is the prior row's entry_hash for this same chain
    (see _chain_key). The payload is canonically serialized (sort_keys) at
    write time and that EXACT string is both stored and hashed — never
    re-serialized before hashing — so any byte-level tampering with the
    stored payload, not just semantic tampering, is detectable.
    """
    chain_key = _chain_key(order_id, payload)
    previous_hash = _previous_entry_hash(db, chain_key)

    payload_json = json.dumps(payload, sort_keys=True)
    created_at = datetime.now(timezone.utc)
    entry_hash = _entry_hash(previous_hash, event_type, payload_json, created_at)

    entry = AuditLog(
        order_id=order_id,
        event_type=event_type,
        payload=payload_json,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@dataclass
class ChainVerificationResult:
    valid: bool
    total_rows: int
    broken_at_row_id: Optional[int] = None
    reason: Optional[str] = None


def verify_chain(db: Session, chain_key: str) -> ChainVerificationResult:
    """Walks one chain in insertion order, recomputing each row's entry_hash
    from its own stored fields and checking the previous_hash linkage.
    Returns the first row where either check fails — everything from that
    row forward is untrustworthy, exactly as a hash chain should behave.
    """
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    chain_rows = []
    for row in rows:
        try:
            row_payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        if _chain_key(row.order_id, row_payload) == chain_key:
            chain_rows.append(row)

    expected_previous = GENESIS_HASH
    for row in chain_rows:
        if row.previous_hash != expected_previous:
            return ChainVerificationResult(False, len(chain_rows), row.id, "previous_hash link broken")

        recomputed = _entry_hash(row.previous_hash, row.event_type, row.payload, row.created_at)
        if recomputed != row.entry_hash:
            return ChainVerificationResult(False, len(chain_rows), row.id, "entry_hash mismatch (tampered)")

        expected_previous = row.entry_hash

    return ChainVerificationResult(True, len(chain_rows))
