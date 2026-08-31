"""Sends deliberately malformed / boundary-value input to
POST /agent/v1/negotiate: negative values, huge values, wrong types,
extra unexpected fields, and a unicode/injection string in the one truly
free-text field this attacker fully controls before any auth check
(buyer_agent_id, via /register).

A PASS here means the input-validation layer (Pydantic) or the
deterministic policy gate caught the bad input — never that the request
was merely "handled" without crashing. A 500 anywhere in this module is
an automatic FAIL — it means untrusted input reached a code path that
wasn't ready for it.
"""

import time

from app.config import settings
from app.report import AttackCase, AttackModuleResult
from app.seller_client import auth_headers, catalog, negotiate_raw
import requests

PRODUCT_ID = 1  # Hand-Painted Ceramic Table Vase — has the tighter 10% cap (see merchant_rules.py)


def _case_result(name: str, description: str, body: dict, resp: requests.Response, expected_note: str) -> AttackCase:
    return AttackCase(
        name=name,
        description=description,
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if expected_note.startswith("PASS") else "FAIL",
        notes=expected_note,
    )


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="malformed_terms", category="tampering")
    buyer_id, api_key = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY

    # 1. Negative value
    body = {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
             "proposed_terms": {"type": "discount", "value": -50000}}
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = resp.status_code == 422
    result.add(AttackCase(
        name="Negative proposed_terms.value",
        description="A negative discount value should never reach the gate as a valid offer — Pydantic's `Field(gt=0)` should reject it at the schema layer, before any business logic runs.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes="Rejected with 422 before reaching the gate, as expected." if ok else f"Expected 422, got {resp.status_code} — negative value was NOT rejected at the validation layer.",
    ))

    # 2. Zero value
    body = {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
             "proposed_terms": {"type": "discount", "value": 0}}
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = resp.status_code == 422
    result.add(AttackCase(
        name="Zero proposed_terms.value",
        description="A zero-value offer (free product) should also be rejected by `Field(gt=0)`.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes="Rejected with 422, as expected." if ok else f"Expected 422, got {resp.status_code}.",
    ))

    # 3. Huge value (bigger than any plausible original price)
    body = {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
             "proposed_terms": {"type": "discount", "value": 10_000_000_000}}
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = False
    note = f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        j = resp.json()
        ok = j.get("approved") is False and j.get("reason") in (
            "discount_value_exceeds_original_price", "below_floor_or_exceeds_max_discount",
        )
        note = (
            f"Gate correctly rejected: approved={j.get('approved')}, reason={j.get('reason')}."
            if ok else f"Gate response did not reject an absurd value as expected: {j}"
        )
    result.add(AttackCase(
        name="Absurdly large proposed_terms.value (10,000,000,000 paise)",
        description="A value far above any real product's price should be deterministically rejected by the gate's own arithmetic (value > total_original), not silently approved.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=note,
    ))

    # 4. Wrong type (string instead of int)
    body = {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
             "proposed_terms": {"type": "discount", "value": "a lot of money please"}}
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = resp.status_code == 422
    result.add(AttackCase(
        name="Wrong type: value as a non-numeric string",
        description="`value` is typed `int`; a non-numeric string should fail request validation, not be coerced or silently dropped.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes="Rejected with 422, as expected." if ok else f"Expected 422, got {resp.status_code}.",
    ))

    # 5. Missing required field
    body = {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
             "proposed_terms": {"type": "discount"}}
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = resp.status_code == 422
    result.add(AttackCase(
        name="Missing required field (proposed_terms.value omitted)",
        description="Omitting a required field should fail validation rather than default to some implicit value.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes="Rejected with 422, as expected." if ok else f"Expected 422, got {resp.status_code}.",
    ))

    # 6. Extra unexpected top-level + nested fields — should be silently
    # ignored (Pydantic's default), never interpreted as an override.
    body = {
        "product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
        "proposed_terms": {"type": "discount", "value": 224910, "override_price": 1, "force_approve": True},
        "is_admin": True,
        "skip_gate": True,
    }
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = False
    note = f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        j = resp.json()
        # Correct behavior: this is evaluated purely on type=discount,
        # value=224910 against product 1's real 10% cap — extra fields
        # must have zero effect on the outcome either way.
        ok = "approved" in j and "force_approve" not in j and "skip_gate" not in j
        note = f"Extra fields ignored; normal gate evaluation proceeded: {j}" if ok else f"Extra fields appear to have leaked into the response or logic: {j}"
    result.add(AttackCase(
        name="Extra unexpected fields (top-level and nested)",
        description="Fields like `is_admin`, `skip_gate`, `override_price` that aren't part of the schema should be silently dropped, never interpreted as instructions.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=note,
    ))

    # 7. Unknown offer type
    body = {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id,
             "proposed_terms": {"type": "cryptocurrency", "value": 100}}
    resp = negotiate_raw(buyer_id, api_key, body)
    ok = resp.status_code == 422
    result.add(AttackCase(
        name="Unknown proposed_terms.type",
        description="`type` is a `Literal[\"discount\", \"bundle\"]`; anything else should fail validation before the gate ever sees it.",
        request=f"POST /agent/v1/negotiate\n{body}",
        actual_response=f"HTTP {resp.status_code}\n{resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes="Rejected with 422, as expected." if ok else f"Expected 422, got {resp.status_code}.",
    ))

    # 8. Unicode / injection string in the one free-text field this
    # attacker fully controls pre-auth: a brand-new buyer_agent_id.
    weird_id = f"红队'; DROP TABLE audit_logs;-- <script>alert(1)</script> \x00 ‮-{int(time.time())}"
    reg_resp = requests.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/register",
        json={"buyer_agent_id": weird_id, "display_name": "'; DROP TABLE products;--"},
        timeout=15,
    )
    ok = False
    note = f"Registration returned HTTP {reg_resp.status_code}: {reg_resp.text}"
    if reg_resp.status_code == 201:
        weird_key = reg_resp.json()["api_key"]
        neg_resp = negotiate_raw(
            weird_id, weird_key,
            {"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": weird_id,
             "proposed_terms": {"type": "discount", "value": 224910}},
        )
        # The real proof the DB wasn't corrupted: the catalog endpoint
        # still works cleanly afterward.
        catalog_resp = catalog()
        ok = neg_resp.status_code == 200 and catalog_resp.status_code == 200 and len(catalog_resp.json()) > 0
        note = (
            f"Registered and negotiated successfully with a SQLi/XSS/null-byte/unicode-bidi buyer_agent_id "
            f"and display_name; string was stored/returned as inert data (SQLAlchemy's parameterized queries, "
            f"not string-formatted SQL). Catalog endpoint still healthy afterward "
            f"({len(catalog_resp.json())} products). negotiate HTTP {neg_resp.status_code}."
            if ok else
            f"negotiate HTTP {neg_resp.status_code}, catalog HTTP {catalog_resp.status_code}: {catalog_resp.text[:300]}"
        )
    result.add(AttackCase(
        name="Unicode / SQL-injection-shaped / XSS-shaped buyer_agent_id",
        description=(
            "Registers a new identity whose buyer_agent_id and display_name contain a SQL-injection-shaped "
            "string, an XSS-shaped string, a null byte, and a Unicode bidi-override character — then confirms "
            "the service doesn't crash and the database isn't corrupted (checked by calling GET /agent/v1/catalog "
            "afterward and confirming it still returns clean data)."
        ),
        request=f"POST /agent/v1/register\n{{'buyer_agent_id': {weird_id!r}, 'display_name': \"'; DROP TABLE products;--\"}}",
        actual_response=note,
        verdict="PASS" if ok else "FAIL",
        notes="SQLAlchemy's ORM parameterizes all queries here — there is no raw string-formatted SQL in this codebase for these fields, so this is expected to hold." if ok else "Investigate immediately — this would be a real SQL injection or crash.",
    ))

    return result
