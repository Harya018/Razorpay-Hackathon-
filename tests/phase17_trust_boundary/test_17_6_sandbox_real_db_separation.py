"""17.6 — Hash-chain sandbox / real-DB separation.

Goal (as specified): confirm the sandbox operates on a copy/snapshot/
in-memory structure, not a live connection to the production audit
DB/table.

REAL ARCHITECTURE (traced end-to-end in backend/app/audit.py +
backend/app/routes/dashboard.py): the premise is not quite right, and
the honest thing to do is correct it rather than write a test around a
wrong mental model. The sandbox does NOT use a separate copy, snapshot,
or in-memory structure — `seed_sandbox_chain()` / `tamper_sandbox_chain()`
/ `get_chain_entries()` all read and write the SAME `audit_logs` TABLE in
the SAME production database, through the exact same `write_audit_log()`
function every real negotiation event goes through. There is no physical
separation at all.

What actually provides isolation is CRYPTOGRAPHIC/LOGICAL, not physical:
every audit row's chain membership is determined by `_chain_key()`
(session:<id> / order:<id> / global), and `verify_chain()` only ever
walks rows matching ONE chain_key, checking each row's `previous_hash`
against the PRECEDING ROW IN THAT SAME CHAIN. The sandbox's rows all
carry session_id="demo:sandbox" (chain_key "session:demo:sandbox"),
which never overlaps a real negotiation's session_id. So tampering with
a sandbox row can only ever break the SANDBOX chain's own internal hash
linkage — it has no way to affect a real chain's stored hashes or
verification result, even though every row lives in the same table.

This test proves that property directly, live: corrupt the sandbox chain,
then independently verify a REAL chain immediately afterward and confirm
it's unaffected. It also proves the "same table" fact explicitly, so this
result doesn't quietly get read as "yes, it's a separate copy" — see
WHAT_BROKE.md for the documentation-vs-reality gap this surfaces.
"""

import sqlite3
from pathlib import Path

import pytest

from conftest import BACKEND_URL, post

BACKEND_DB_PATH = Path(__file__).resolve().parents[2] / "backend" / "app.db"


def _independent_row_count(chain_key_like: str) -> int:
    """A completely separate sqlite3 connection (not through the backend's
    API at all) — an independent, out-of-band check that sandbox rows
    really do live in the same physical table as everything else.
    """
    con = sqlite3.connect(f"file:{BACKEND_DB_PATH}?mode=ro", uri=True)
    try:
        cur = con.execute("SELECT COUNT(*) FROM audit_logs WHERE payload LIKE ?", (f"%{chain_key_like}%",))
        return cur.fetchone()[0]
    finally:
        con.close()


def test_sandbox_rows_share_the_real_audit_logs_table(evidence):
    """Out-of-band proof (a raw sqlite3 connection, bypassing the API
    entirely) that sandbox rows are ordinary rows in the SAME table as
    every real negotiation/order event — not a separate structure.
    """
    if not BACKEND_DB_PATH.exists():
        pytest.skip(f"backend DB not found at {BACKEND_DB_PATH} (only works against the local SQLite deployment)")

    post(f"{BACKEND_URL}/dashboard/audit-trail/sandbox/reset", {})
    sandbox_row_count = _independent_row_count("demo:sandbox")

    evidence.record(
        "raw_sqlite_query",
        db_path=str(BACKEND_DB_PATH),
        sandbox_rows_in_audit_logs_table=sandbox_row_count,
        note="Queried directly against audit_logs — the SAME table dashboard_negotiations() reads for real sessions.",
    )
    evidence.flush(
        "CONFIRMED: shared table, not a separate copy",
        notes=f"{sandbox_row_count} sandbox rows found living in the production audit_logs table.",
    )

    assert sandbox_row_count > 0, "Sandbox rows should exist in audit_logs after a reset — investigate seeding."
    # This assertion is the actual finding: the task's premise (a
    # copy/snapshot/in-memory structure) does not hold. Documented in
    # WHAT_BROKE.md rather than silently treated as a pass/fail either way.


def test_tampering_sandbox_does_not_break_real_chain_verification(evidence):
    """The property that actually matters: does corrupting the sandbox
    chain have any observable effect on a REAL chain's own integrity
    check? Verified live, independently, immediately after tampering.
    """
    # Establish a real chain to check against — the most recently active
    # one, exactly what the Audit Trail panel itself displays.
    before = post(f"{BACKEND_URL}/dashboard/audit-trail/verify", {}).json()
    evidence.record("real_chain_verify_before_tamper", response=before)

    if before.get("chain_key") is None:
        pytest.skip("No real negotiation chain exists yet to verify against — run a negotiation first.")

    real_chain_key = before["chain_key"]
    assert before["valid"] is True, "Real chain must be valid BEFORE the sandbox tamper to make this a meaningful test."

    # Reset then corrupt the sandbox chain.
    post(f"{BACKEND_URL}/dashboard/audit-trail/sandbox/reset", {})
    tamper_resp = post(f"{BACKEND_URL}/dashboard/audit-trail/sandbox/tamper", {}).json()
    evidence.record("sandbox_tamper", response=tamper_resp)

    sandbox_verify = post(f"{BACKEND_URL}/dashboard/audit-trail/sandbox/verify", {}).json()
    evidence.record("sandbox_verify_after_tamper", response=sandbox_verify)
    assert sandbox_verify["valid"] is False, "Sandbox tamper action should have broken the sandbox chain — it didn't."

    # The actual assertion: re-verify the REAL chain, independently, right after.
    after = post(f"{BACKEND_URL}/dashboard/audit-trail/verify", {}).json()
    evidence.record("real_chain_verify_after_tamper", response=after)

    verdict = "PASS" if after.get("chain_key") == real_chain_key and after.get("valid") is True else "FAIL"
    evidence.flush(
        verdict,
        notes="Real chain integrity is unaffected by sandbox tampering, despite sharing a physical table — "
        "isolation is provided by chain_key scoping + per-chain hash linkage, not physical separation.",
    )

    assert after.get("chain_key") == real_chain_key, "The active real chain changed identity — investigate."
    assert after.get("valid") is True, (
        f"SECURITY BUG: tampering with the SANDBOX chain broke verification of the REAL chain "
        f"({real_chain_key}): {after}"
    )

    # Cleanup: leave the sandbox in a clean state for the dashboard demo.
    post(f"{BACKEND_URL}/dashboard/audit-trail/sandbox/reset", {})
