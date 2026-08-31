"""Direct SQLite access to the SAME database files the backend and
policy-gate processes use — deliberately bypassing the application layer
entirely. Used ONLY by attacks whose entire point is "what happens if
someone with filesystem access writes to these tables directly," which by
definition cannot be done through the HTTP API or an import.

Table/column names here were read from the actual model files
(backend/app/models/*.py, policy-gate/app/models/approval.py) — not
guessed — since a wrong column name would make these attacks silently
no-op instead of actually testing anything.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from app.config import settings


def _connect(db_path: str) -> sqlite3.Connection:
    resolved = Path(__file__).parent.parent / db_path
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    return conn


def backend_db() -> sqlite3.Connection:
    return _connect(settings.BACKEND_DB_PATH)


def policy_gate_db() -> sqlite3.Connection:
    return _connect(settings.POLICY_GATE_DB_PATH)


def get_product_price(product_id: int) -> int:
    with backend_db() as conn:
        row = conn.execute("SELECT price FROM products WHERE id = ?", (product_id,)).fetchone()
        return row["price"]


def set_product_price(product_id: int, new_price: int) -> None:
    with backend_db() as conn:
        conn.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, product_id))
        conn.commit()


def backdate_approval(approval_token: str, iso_timestamp: str) -> int:
    """Sets an approval row's created_at to an arbitrary (e.g. far-past)
    timestamp. Returns the number of rows affected (0 means the token
    wasn't found — callers should treat that as a setup failure).
    """
    with policy_gate_db() as conn:
        cur = conn.execute(
            "UPDATE approvals SET created_at = ? WHERE approval_token = ?", (iso_timestamp, approval_token)
        )
        conn.commit()
        return cur.rowcount


def insert_fake_audit_row(event_type: str, payload_json: str, previous_hash: str, entry_hash: str, created_at_iso: str) -> int:
    """Writes an audit_logs row directly via raw SQL — exactly what an
    attacker with filesystem/DB access (but not application-layer access)
    could do. Returns the new row's id.
    """
    with backend_db() as conn:
        cur = conn.execute(
            "INSERT INTO audit_logs (order_id, event_type, payload, previous_hash, entry_hash, created_at) "
            "VALUES (NULL, ?, ?, ?, ?, ?)",
            (event_type, payload_json, previous_hash, entry_hash, created_at_iso),
        )
        conn.commit()
        return cur.lastrowid


def tamper_audit_row_payload(row_id: int, new_payload_json: str) -> None:
    """The actual attack: rewrite an EXISTING row's payload in place —
    e.g. changing a recorded discount amount after the fact — without
    touching entry_hash, exactly as an attacker who only knows "there's a
    payload column with JSON in it" would do.
    """
    with backend_db() as conn:
        conn.execute("UPDATE audit_logs SET payload = ? WHERE id = ?", (new_payload_json, row_id))
        conn.commit()


def fetch_audit_chain_rows(session_id_marker: str) -> list[sqlite3.Row]:
    """Reads back every audit_logs row belonging to one session's chain,
    in insertion order — the same rows an independent verifier needs.
    """
    with backend_db() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY id ASC").fetchall()
        return [r for r in rows if session_id_marker in (r["payload"] or "")]


def max_audit_id() -> int:
    with backend_db() as conn:
        row = conn.execute("SELECT MAX(id) AS max_id FROM audit_logs").fetchone()
        return row["max_id"] or 0


def fetch_audit_rows_by_id_range(start_id_exclusive: int, end_id_inclusive: int) -> list[sqlite3.Row]:
    with backend_db() as conn:
        return conn.execute(
            "SELECT * FROM audit_logs WHERE id > ? AND id <= ? ORDER BY id ASC",
            (start_id_exclusive, end_id_inclusive),
        ).fetchall()


def get_order_by_razorpay_id(razorpay_order_id: str) -> Optional[sqlite3.Row]:
    """The human-checkout endpoints (/order/create) only ever return
    razorpay_order_id to the caller, never the backend's own internal
    integer order id or its live status — reading it back requires either
    the agent-channel's /agent/v1/order/{id}/status (keyed by the internal
    id we don't have) or, as here, direct DB access, same declared
    exception as this module's other helpers.
    """
    with backend_db() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE razorpay_order_id = ?", (razorpay_order_id,)
        ).fetchone()


def count_audit_rows_for_order(order_id: int, event_type: Optional[str] = None) -> int:
    with backend_db() as conn:
        if event_type is not None:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM audit_logs WHERE order_id = ? AND event_type = ?",
                (order_id, event_type),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM audit_logs WHERE order_id = ?", (order_id,)
            ).fetchone()
        return row["n"]
