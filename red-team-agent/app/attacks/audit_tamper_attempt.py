"""Attempts to write directly to backend/app.db's audit_logs table via
raw SQL — the same file the application uses, bypassing FastAPI, the ORM,
and write_audit_log() entirely — then runs an INDEPENDENT reimplementation
of the hash-chain verifier (app/chain_verify.py, not imported from
backend) to confirm it detects the tamper.

This is the one attack in this suite that has legitimate, intended access
to direct DB writes (see db_direct.py's docstring) — everywhere else,
going around the HTTP API would defeat the point of the test.
"""

import json

from app.chain_verify import verify_chain
from app.config import settings
from app.db_direct import fetch_audit_rows_by_id_range, max_audit_id, tamper_audit_row_payload
from app.report import AttackCase, AttackModuleResult
from app.seller_client import negotiate

PRODUCT_ID = 1


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="audit_tamper_attempt", category="tampering")
    buyer_id, api_key = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY

    # 1. Generate a real, small hash-chained pair of rows to attack:
    # agent_negotiate_requested -> agent_negotiate_decided for one call.
    id_before = max_audit_id()
    neg_resp = negotiate(buyer_id, api_key, PRODUCT_ID, 1, "discount", 240000)  # within the 10% cap on product 1
    neg_resp.raise_for_status()
    id_after = max_audit_id()

    rows_before = fetch_audit_rows_by_id_range(id_before, id_after)
    baseline_valid, baseline_break_id, baseline_reason = verify_chain(rows_before)

    if not baseline_valid or len(rows_before) < 2:
        result.add(AttackCase(
            name="Sanity baseline — untampered chain verifies clean",
            description="Before tampering with anything, confirm the independent verifier agrees the freshly-written chain is valid — otherwise a later 'detected!' result would be meaningless.",
            request=f"verify_chain() over rows {[r['id'] for r in rows_before]}",
            actual_response=f"valid={baseline_valid}, broken_at={baseline_break_id}, reason={baseline_reason}, row_count={len(rows_before)}",
            verdict="FAIL",
            notes="Could not establish a clean baseline — either the negotiate call didn't produce the expected 2-row chain, or the independent verifier disagrees with the write path even before any tampering. Investigate before trusting the tamper-detection result below.",
        ))
        return result

    result.add(AttackCase(
        name="Sanity baseline — untampered chain verifies clean",
        description="Confirms the independent verifier (reimplemented from audit.py's documented algorithm, not imported) agrees this freshly-written 2-row chain is valid before any tampering — establishes that a later detection is meaningful, not a false positive.",
        request=f"verify_chain() over fresh rows {[r['id'] for r in rows_before]}",
        actual_response=f"valid=True, {len(rows_before)} rows checked",
        verdict="PASS",
        notes="Baseline established; proceeding to tamper.",
    ))

    # 2. The attack: directly rewrite one row's payload — the
    # agent_negotiate_decided row — via raw SQL, changing a rejected/low
    # offer's recorded terms into an approved one, WITHOUT touching
    # previous_hash or entry_hash (the naive, most realistic attacker
    # move — someone with DB file access but no knowledge of, or ability
    # to recompute, this specific SHA-256 chain).
    target_row = rows_before[-1]  # agent_negotiate_decided
    original_payload = json.loads(target_row["payload"])
    forged_payload = dict(original_payload)
    forged_payload["approved"] = True
    forged_payload["reason"] = None
    forged_payload["max_allowed"] = None
    forged_payload["final_terms"] = {"type": "discount", "value": 1}  # absurd forged discount
    forged_payload_json = json.dumps(forged_payload, sort_keys=True)

    tamper_audit_row_payload(target_row["id"], forged_payload_json)

    rows_after = fetch_audit_rows_by_id_range(id_before, id_after)
    post_valid, break_id, reason = verify_chain(rows_after)

    ok = (not post_valid) and (break_id == target_row["id"]) and (reason == "entry_hash mismatch (tampered)")
    result.add(AttackCase(
        name="Direct SQL tamper of an existing audit_logs row's payload",
        description=(
            f"Rewrites row id={target_row['id']} (event_type=agent_negotiate_decided) via a raw "
            f"`UPDATE audit_logs SET payload = ? WHERE id = ?` — bypassing write_audit_log(), the ORM, and every "
            f"application-layer check — forging a rejected/modest offer into an approved discount of ₹0.01, "
            f"without touching previous_hash or entry_hash."
        ),
        request=(
            f"Original payload: {json.dumps(original_payload, sort_keys=True)}\n"
            f"Forged payload written directly to SQLite: {forged_payload_json}"
        ),
        actual_response=f"Independent verify_chain() result: valid={post_valid}, broken_at_row_id={break_id}, reason={reason!r}",
        verdict="PASS" if ok else "FAIL",
        notes=(
            "The hash chain correctly flagged the exact tampered row as an entry_hash mismatch, and everything "
            "from that row forward is now correctly untrustworthy per the chain's own design."
            if ok else
            "The tamper was NOT detected, or was attributed to the wrong row — this would mean the hash chain "
            "gives false confidence. Needs immediate investigation."
        ),
    ))

    return result
