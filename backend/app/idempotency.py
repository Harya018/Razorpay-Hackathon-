import json
import hashlib
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyRecord


def request_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_idempotent(db: Session, scope: str, key: str | None, payload: Any, fn: Callable[[], dict]) -> dict:
    if not key:
        return fn()

    digest = request_hash(payload)
    existing = db.query(IdempotencyRecord).filter(
        IdempotencyRecord.scope == scope,
        IdempotencyRecord.idempotency_key == key,
    ).first()
    if existing is not None:
        if existing.request_hash != digest:
            raise HTTPException(status_code=409, detail="Idempotency key was already used for a different request")
        return json.loads(existing.response_json)

    response = fn()
    record = IdempotencyRecord(
        scope=scope,
        idempotency_key=key,
        request_hash=digest,
        response_json=json.dumps(response, sort_keys=True, default=str),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(IdempotencyRecord).filter(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == key,
        ).first()
        if existing is not None and existing.request_hash == digest:
            return json.loads(existing.response_json)
        raise HTTPException(status_code=409, detail="Idempotency key conflict")
    return response