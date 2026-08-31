import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.audit import chain_key_for_session, verify_chain, write_audit_log
from app.database import Base
from app.models import order, product  # noqa: F401 — registers FK targets (orders, products) on Base.metadata
from app.models.audit_log import AuditLog


def _isolated_session():
    """A fresh in-memory DB per test — never touches the real app.db."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_valid_chain_verifies():
    db = _isolated_session()
    session_id = "test-session-valid"
    write_audit_log(db, None, "cart_assessed", {"session_id": session_id, "step": 1})
    write_audit_log(db, None, "offer_decision", {"session_id": session_id, "step": 2})
    write_audit_log(db, None, "offer_proposed", {"session_id": session_id, "step": 3})

    result = verify_chain(db, chain_key_for_session(session_id))

    assert result.valid
    assert result.total_rows == 3
    assert result.broken_at_row_id is None


def test_tampering_breaks_chain_from_that_row_forward():
    db = _isolated_session()
    session_id = "test-session-tampered"
    write_audit_log(db, None, "cart_assessed", {"session_id": session_id, "step": 1})
    write_audit_log(db, None, "offer_decision", {"session_id": session_id, "step": 2})
    write_audit_log(db, None, "offer_proposed", {"session_id": session_id, "step": 3})

    # Sanity check: untampered chain verifies before we touch anything.
    assert verify_chain(db, chain_key_for_session(session_id)).valid

    # Tamper with the SECOND row's payload directly, as an attacker with
    # raw DB access would — bypassing write_audit_log entirely.
    second_row = db.query(AuditLog).filter(AuditLog.event_type == "offer_decision").one()
    tampered_payload = json.loads(second_row.payload)
    tampered_payload["step"] = 999
    second_row.payload = json.dumps(tampered_payload, sort_keys=True)
    db.commit()

    result = verify_chain(db, chain_key_for_session(session_id))

    assert not result.valid
    assert result.broken_at_row_id == second_row.id
    assert result.reason == "entry_hash mismatch (tampered)"


def test_tampering_previous_hash_is_also_detected():
    db = _isolated_session()
    session_id = "test-session-relink"
    write_audit_log(db, None, "cart_assessed", {"session_id": session_id, "step": 1})
    write_audit_log(db, None, "offer_decision", {"session_id": session_id, "step": 2})

    second_row = db.query(AuditLog).filter(AuditLog.event_type == "offer_decision").one()
    # Simulate an attacker deleting the first row and re-linking the second
    # row's previous_hash to genesis, trying to hide that a row is missing.
    second_row.previous_hash = "0" * 64
    db.commit()

    result = verify_chain(db, chain_key_for_session(session_id))

    assert not result.valid
    assert result.broken_at_row_id == second_row.id
    # Caught by the link check rather than the hash-recompute check — a
    # different detection path than the payload-tampering test above, but
    # equally valid: either way, tampering is caught at exactly this row.
    assert result.reason == "previous_hash link broken"


def test_chains_are_isolated_per_session():
    db = _isolated_session()
    write_audit_log(db, None, "cart_assessed", {"session_id": "session-a", "step": 1})
    write_audit_log(db, None, "cart_assessed", {"session_id": "session-b", "step": 1})
    write_audit_log(db, None, "offer_decision", {"session_id": "session-a", "step": 2})

    result_a = verify_chain(db, chain_key_for_session("session-a"))
    result_b = verify_chain(db, chain_key_for_session("session-b"))

    assert result_a.valid and result_a.total_rows == 2
    assert result_b.valid and result_b.total_rows == 1
