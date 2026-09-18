"""Pure unit tests for app/idempotency.py — no live services needed, an
in-memory DB per test, same isolation pattern as test_audit_hash_chain.py.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.idempotency import request_hash, run_idempotent
from app.models.idempotency import IdempotencyRecord  # noqa: F401 — registers the table


def _isolated_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_request_hash_is_order_independent():
    # sort_keys=True means field order in the input dict shouldn't matter —
    # a client re-serializing the "same" JSON body with keys in a
    # different order must still be recognized as the same request.
    a = request_hash({"product_id": 1, "quantity": 2})
    b = request_hash({"quantity": 2, "product_id": 1})
    assert a == b


def test_run_idempotent_without_a_key_always_calls_fn():
    db = _isolated_session()
    calls = []

    def fn():
        calls.append(1)
        return {"ok": True}

    run_idempotent(db, "scope", None, {"x": 1}, fn)
    run_idempotent(db, "scope", None, {"x": 1}, fn)
    assert len(calls) == 2  # no key => no dedup, every call is real


def test_run_idempotent_same_key_same_payload_calls_fn_once():
    db = _isolated_session()
    calls = []

    def fn():
        calls.append(1)
        return {"session_id": "abc123"}

    r1 = run_idempotent(db, "negotiate_start", "key-1", {"product_id": 1}, fn)
    r2 = run_idempotent(db, "negotiate_start", "key-1", {"product_id": 1}, fn)

    assert len(calls) == 1  # the second call is served from the stored response, fn() never re-runs
    assert r1 == r2 == {"session_id": "abc123"}


def test_run_idempotent_same_key_different_payload_is_rejected():
    db = _isolated_session()

    run_idempotent(db, "negotiate_start", "key-1", {"product_id": 1}, lambda: {"ok": True})

    with pytest.raises(HTTPException) as exc_info:
        run_idempotent(db, "negotiate_start", "key-1", {"product_id": 2}, lambda: {"ok": True})
    assert exc_info.value.status_code == 409


def test_run_idempotent_different_scopes_do_not_collide():
    # The same key used for two DIFFERENT endpoints (scopes) must not be
    # treated as the same logical request just because the string matches.
    db = _isolated_session()
    calls = []

    def fn():
        calls.append(1)
        return {"n": len(calls)}

    r1 = run_idempotent(db, "negotiate_start", "shared-key", {"x": 1}, fn)
    r2 = run_idempotent(db, "order_create", "shared-key", {"x": 1}, fn)

    assert len(calls) == 2
    assert r1 != r2
