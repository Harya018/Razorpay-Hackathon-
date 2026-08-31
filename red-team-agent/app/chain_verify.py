"""An INDEPENDENT reimplementation of backend/app/audit.py's hash-chain
verification — deliberately not imported (this project's buyer-agent and
red-team-agent both follow a no-backend-imports rule; see their READMEs).

The algorithm is taken from audit.py's own docstring, which states it
plainly as public contract:

    entry_hash = sha256(previous_hash | event_type | payload | created_at)

where `payload` is the EXACT JSON string stored in the row (never
re-serialized before hashing) and `created_at` is hashed as its naive
(tzinfo-stripped) ISO-8601 form — audit.py notes this explicitly, because
SQLite drops datetime tzinfo on round-trip and the hash must be computed
the same way on write and on read for the chain to verify at all.

Reading the row via raw sqlite3 (as this module does, on purpose, for the
tamper attack) returns created_at as SQLite's own stored text format
("YYYY-MM-DD HH:MM:SS.ffffff"), not Python's ISO format ("...THH:MM:SS...")
— it must be parsed and re-formatted to match what SQLAlchemy's DateTime
column would have produced, or every hash would appear to mismatch even
on an untampered chain.
"""

import hashlib
from datetime import datetime

GENESIS_HASH = "0" * 64


def _normalize_created_at(raw_value: str) -> str:
    dt = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S.%f")
    return dt.isoformat()


def entry_hash(previous_hash: str, event_type: str, payload_json: str, created_at_raw: str) -> str:
    naive_iso = _normalize_created_at(created_at_raw)
    return hashlib.sha256(f"{previous_hash}|{event_type}|{payload_json}|{naive_iso}".encode("utf-8")).hexdigest()


def verify_chain(rows: list) -> tuple[bool, int | None, str | None]:
    """rows: sqlite3.Row objects (or any mapping with previous_hash,
    entry_hash, event_type, payload, created_at, id), already filtered to
    one chain and sorted by id ascending — mirrors audit.verify_chain's
    contract exactly. Returns (valid, broken_at_row_id, reason).
    """
    expected_previous = GENESIS_HASH
    for row in rows:
        if row["previous_hash"] != expected_previous:
            return False, row["id"], "previous_hash link broken"
        recomputed = entry_hash(row["previous_hash"], row["event_type"], row["payload"], row["created_at"])
        if recomputed != row["entry_hash"]:
            return False, row["id"], "entry_hash mismatch (tampered)"
        expected_previous = row["entry_hash"]
    return True, None, None
