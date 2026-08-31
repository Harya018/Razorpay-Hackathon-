"""x402 V2 wire-format conformance test — a judge can run this directly
against a live instance of the catalog service (`python x402_conformance_test.py`,
from inside redteam/ with its own venv active) and see, per requirement,
whether this deployment's /agent/v1/* interface actually matches the real
x402 V2 spec, not just "looks x402-shaped."

Every check below maps to a row in docs/x402-conformance-diff.md — this
script is that checklist made executable and re-runnable, not a separate
list of assertions invented independently of it. HTTP-only, no imports
from backend source, same independence discipline as the rest of this
suite.

Prints ONE pass/fail line per spec requirement (not a single aggregate
pass/fail), then writes the full result set to
results/x402-conformance-results.json in the same schema every other
module in this suite uses.
"""

import base64
import json
import sys
import uuid

import httpx

from config import settings
from report import AttackResult

PRODUCT_ID = 1  # Hand-Painted Ceramic Table Vase

EXPECTED_DISCLAIMER = (
    "Settlement is processed via Razorpay (India, fiat, test-mode). This is not an "
    "onchain settlement network. network values under the inr-fiat: prefix are a "
    "documented x402 extension for this deployment, not part of the core x402 "
    "network registry."
)

_client = httpx.Client(timeout=30)


def _register() -> tuple[str, str]:
    buyer_id = f"x402conformance-{uuid.uuid4().hex[:10]}"
    resp = _client.post(f"{settings.SELLER_BASE_URL}/agent/v1/register", json={"buyer_agent_id": buyer_id})
    resp.raise_for_status()
    return buyer_id, resp.json()["api_key"]


def _decode_header(value: str) -> dict:
    return json.loads(base64.b64decode(value))


def _check(checks: list[AttackResult], req_id: str, description: str, passed: bool, notes: str) -> None:
    result = AttackResult(
        attack_id=f"x402_conformance.{req_id}",
        description=description,
        requests_sent=1,
        expected_successes=1,
        actual_successes=1 if passed else 0,
        blocked=passed,
        verdict="PASS" if passed else "FAIL",
        notes=notes,
    )
    checks.append(result)
    print(f"[{result.verdict}] {req_id} — {description}")
    print(f"    {notes}")


def run() -> list[AttackResult]:
    checks: list[AttackResult] = []
    base = settings.SELLER_BASE_URL

    # --- Setup: catalog, discovery, register, negotiate, purchase --------

    catalog_resp = _client.get(f"{base}/agent/v1/catalog")
    catalog = catalog_resp.json() if catalog_resp.status_code == 200 else []
    product = next((p for p in catalog if p["id"] == PRODUCT_ID), catalog[0] if catalog else None)

    _check(
        checks, "catalog_settlement_type",
        "Every catalog item carries settlement_type: 'fiat' directly, before an agent ever reaches a payment endpoint.",
        product is not None and product.get("settlement_type") == "fiat",
        f"catalog[0]: {product}",
    )

    discovery_resp = _client.get(f"{base}/agent/v1/discovery")
    discovery = discovery_resp.json() if discovery_resp.status_code == 200 else {}

    _check(
        checks, "discovery_x402_version",
        "GET /agent/v1/discovery declares x402Version == 2.",
        discovery.get("x402Version") == 2,
        f"discovery.x402Version = {discovery.get('x402Version')!r}",
    )
    _check(
        checks, "discovery_disclaimer_verbatim",
        "GET /agent/v1/discovery's extensionDisclaimer matches the required sentence VERBATIM.",
        discovery.get("extensionDisclaimer") == EXPECTED_DISCLAIMER,
        f"discovery.extensionDisclaimer = {discovery.get('extensionDisclaimer')!r}",
    )

    buyer_id, api_key = _register()
    headers = {"Authorization": f"Bearer {api_key}"}

    purchase_resp = _client.post(
        f"{base}/agent/v1/purchase",
        headers=headers,
        json={"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id, "approval_token": None},
    )

    _check(
        checks, "purchase_returns_402",
        "POST /agent/v1/purchase returns HTTP 402 (the spec's payment-required signal), not 200.",
        purchase_resp.status_code == 402,
        f"HTTP {purchase_resp.status_code}",
    )

    pr_header = purchase_resp.headers.get("PAYMENT-REQUIRED")
    _check(
        checks, "payment_required_header_present",
        "The 402 response carries a PAYMENT-REQUIRED header (base64-encoded JSON), not just a JSON body.",
        pr_header is not None,
        f"PAYMENT-REQUIRED header present: {pr_header is not None}",
    )

    decoded_pr = {}
    if pr_header:
        try:
            decoded_pr = _decode_header(pr_header)
        except Exception as e:
            _check(checks, "payment_required_decodes", "PAYMENT-REQUIRED header decodes as base64 JSON.", False, str(e))

    _check(
        checks, "payment_required_x402_version",
        "PAYMENT-REQUIRED.x402Version == 2.",
        decoded_pr.get("x402Version") == 2,
        f"x402Version = {decoded_pr.get('x402Version')!r}",
    )
    _check(
        checks, "resource_is_top_level",
        "PAYMENT-REQUIRED.resource is a TOP-LEVEL object (spec 5.1.2), not nested inside each accepts[] entry.",
        isinstance(decoded_pr.get("resource"), dict) and "url" in decoded_pr.get("resource", {}),
        f"resource = {decoded_pr.get('resource')!r}",
    )

    accepts = decoded_pr.get("accepts") or [{}]
    entry = accepts[0]
    required_pr_fields = ["scheme", "network", "amount", "asset", "payTo", "maxTimeoutSeconds"]
    missing = [f for f in required_pr_fields if f not in entry]
    _check(
        checks, "payment_requirements_shape",
        "accepts[0] has every required PaymentRequirements field: scheme, network, amount, asset, payTo, maxTimeoutSeconds.",
        not missing,
        f"accepts[0] keys = {sorted(entry.keys())}, missing = {missing}",
    )
    _check(
        checks, "amount_is_string",
        "accepts[0].amount is a string (atomic units), not a number — the spec's actual type, not 'maxAmountRequired'.",
        isinstance(entry.get("amount"), str),
        f"amount = {entry.get('amount')!r} (type {type(entry.get('amount')).__name__})",
    )
    network = entry.get("network", "")
    _check(
        checks, "network_is_caip2_shaped_non_registry",
        "network is CAIP-2-SHAPED (namespace:reference) but under the documented inr-fiat: prefix, never a real registered namespace like eip155: or solana:.",
        network == "inr-fiat:razorpay-test" and ":" in network and not network.startswith(("eip155:", "solana:")),
        f"network = {network!r}",
    )
    _check(
        checks, "settlement_type_never_onchain",
        "accepts[0].extra.settlementType is 'fiat-custodial', never 'onchain'.",
        (entry.get("extra") or {}).get("settlementType") == "fiat-custodial",
        f"extra.settlementType = {(entry.get('extra') or {}).get('settlementType')!r}",
    )

    extensions = decoded_pr.get("extensions") or {}
    _check(
        checks, "extensions_mechanism_populated",
        "PAYMENT-REQUIRED.extensions carries the spec's own formal {info, schema} shape (not just an informal disclaimer elsewhere).",
        isinstance(extensions.get("info"), dict) and isinstance(extensions.get("schema"), dict),
        f"extensions keys = {sorted(extensions.keys())}",
    )
    disclaimer_in_extensions = (extensions.get("info") or {}).get("inr-fiat", {}).get("disclaimer")
    _check(
        checks, "extensions_disclaimer_verbatim",
        "The verbatim disclaimer is ALSO machine-discoverable via extensions.info, not just the discovery endpoint's prose field.",
        disclaimer_in_extensions == EXPECTED_DISCLAIMER,
        f"extensions.info.inr-fiat.disclaimer = {disclaimer_in_extensions!r}",
    )

    terms_reference = purchase_resp.json().get("terms_reference")

    # --- /pay: missing / malformed / incomplete PAYMENT-SIGNATURE ---------

    resp_missing = _client.post(
        f"{base}/agent/v1/pay",
        headers=headers,
        json={"terms_reference": terms_reference, "approval_token": None, "buyer_agent_id": buyer_id},
    )
    _check(
        checks, "missing_signature_rejected",
        "POST /agent/v1/pay with NO PAYMENT-SIGNATURE header is rejected with a clear 4xx, never a silent pass-through.",
        400 <= resp_missing.status_code < 500,
        f"HTTP {resp_missing.status_code}: {resp_missing.text[:150]}",
    )

    resp_malformed = _client.post(
        f"{base}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": "not-valid-base64!!!"},
        json={"terms_reference": terms_reference, "approval_token": None, "buyer_agent_id": buyer_id},
    )
    _check(
        checks, "malformed_signature_rejected",
        "POST /agent/v1/pay with a non-base64 PAYMENT-SIGNATURE is rejected with a clear 4xx.",
        400 <= resp_malformed.status_code < 500,
        f"HTTP {resp_malformed.status_code}: {resp_malformed.text[:150]}",
    )

    incomplete_payload = base64.b64encode(json.dumps({
        "x402Version": 2,
        "payload": {"custodialReceipt": {"terms_reference": terms_reference, "approval_token": None}},
    }).encode()).decode()
    resp_incomplete = _client.post(
        f"{base}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": incomplete_payload},
        json={"terms_reference": terms_reference, "approval_token": None, "buyer_agent_id": buyer_id},
    )
    _check(
        checks, "payment_payload_requires_accepted",
        "PAYMENT-SIGNATURE missing the required 'accepted' field (PaymentRequirements) is rejected, not silently accepted with the old flattened scheme/network shape.",
        400 <= resp_incomplete.status_code < 500,
        f"HTTP {resp_incomplete.status_code}: {resp_incomplete.text[:200]}",
    )

    # --- /pay: a real, correctly-shaped signature succeeds -----------------

    good_payload = base64.b64encode(json.dumps({
        "x402Version": 2,
        "accepted": entry,
        "payload": {"custodialReceipt": {"terms_reference": terms_reference, "approval_token": None}},
    }).encode()).decode()
    resp_pay = _client.post(
        f"{base}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": good_payload},
        json={"terms_reference": terms_reference, "approval_token": None, "buyer_agent_id": buyer_id},
    )
    _check(
        checks, "correctly_shaped_signature_succeeds",
        "A correctly-shaped PAYMENT-SIGNATURE (with accepted) is accepted and settles the payment.",
        resp_pay.status_code == 200,
        f"HTTP {resp_pay.status_code}: {resp_pay.text[:200]}",
    )

    presp_header = resp_pay.headers.get("PAYMENT-RESPONSE")
    _check(
        checks, "payment_response_header_present_on_success",
        "PAYMENT-RESPONSE header present on a successful settlement.",
        presp_header is not None,
        f"PAYMENT-RESPONSE present: {presp_header is not None}",
    )

    decoded_presp = _decode_header(presp_header) if presp_header else {}
    _check(
        checks, "settlement_response_shape",
        "SettlementResponse has success=True, settlementType='fiat-custodial' (never 'onchain'), transaction (non-empty string), network.",
        decoded_presp.get("success") is True
        and decoded_presp.get("settlementType") == "fiat-custodial"
        and bool(decoded_presp.get("transaction"))
        and bool(decoded_presp.get("network")),
        f"decoded PAYMENT-RESPONSE = {decoded_presp}",
    )
    _check(
        checks, "transaction_is_not_fabricated_payment_id",
        "SettlementResponse.transaction is a Razorpay order id (order_...), never a fabricated payment id (pay_...) — capture is asynchronous, no payment id exists yet at this point.",
        str(decoded_presp.get("transaction", "")).startswith("order_"),
        f"transaction = {decoded_presp.get('transaction')!r}",
    )

    # --- /pay: reused terms_reference -> 402, not 404, per spec's own mapping --

    resp_reused = _client.post(
        f"{base}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": good_payload},
        json={"terms_reference": terms_reference, "approval_token": None, "buyer_agent_id": buyer_id},
    )
    _check(
        checks, "payment_failure_uses_402_not_404",
        "A settlement failure (reused/unknown terms_reference) uses HTTP 402 per the spec's own status mapping ('402 used for payment-required AND payment-failed'), not a generic 404.",
        resp_reused.status_code == 402,
        f"HTTP {resp_reused.status_code}: {resp_reused.text[:150]}",
    )
    _check(
        checks, "payment_response_present_on_failure_too",
        "PAYMENT-RESPONSE is attached on the FAILURE path too, not just success — the spec's own examples show both.",
        resp_reused.headers.get("PAYMENT-RESPONSE") is not None,
        f"PAYMENT-RESPONSE present on failure: {resp_reused.headers.get('PAYMENT-RESPONSE') is not None}",
    )

    # --- No deprecated X-* headers anywhere in this flow --------------------

    all_header_names = set(purchase_resp.headers.keys()) | set(resp_pay.headers.keys()) | set(resp_reused.headers.keys())
    deprecated = [h for h in all_header_names if h.upper().startswith("X-PAYMENT")]
    _check(
        checks, "no_deprecated_x_headers",
        "No deprecated X-PAYMENT-* style headers appear anywhere in this flow — only PAYMENT-REQUIRED/PAYMENT-SIGNATURE/PAYMENT-RESPONSE.",
        not deprecated,
        f"Deprecated-shaped headers found: {deprecated}",
    )

    return checks


def main() -> int:
    checks = run()

    # Same AttackResult schema every other module in this suite uses
    # (report.py), written directly to the exact contracted filename
    # rather than through write_results()'s {category}_results.json
    # naming convention, which doesn't match "x402-conformance-results.json".
    from pathlib import Path
    out_path = Path(__file__).parent / "results" / "x402-conformance-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([c.to_dict() for c in checks], indent=2, ensure_ascii=False), encoding="utf-8"
    )

    total = len(checks)
    failed = sum(1 for c in checks if c.verdict == "FAIL")
    print(f"\n=== SUMMARY: {total - failed}/{total} conformance checks passed, {failed} failed ===")
    print(f"wrote {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
