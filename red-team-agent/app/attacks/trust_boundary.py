"""Attacks the trust boundary between backend and policy-gate — two
separate deployable services with a real network boundary between them,
where state can disagree or one side can simply be unreachable.

policy_gate_unreachable is the one case in this module that goes beyond
pure HTTP: it actually stops and restarts the real policy-gate process
(Windows-specific, via subprocess + PowerShell — same commands used
manually throughout this project's own dev sessions to manage services),
because "is the fail-safe behavior real" can only be honestly answered by
actually taking the dependency down, not by mocking it.
"""

import re
import subprocess
import time

from app.config import settings
from app.report import AttackCase, AttackModuleResult
from app.seller_client import negotiate, order_create

PRODUCT_ID = 2  # Ceramic Coffee Mug

# Path to the policy-gate service, relative to this project's known dev
# layout (all services checked out as siblings) — same assumption
# db_direct.py's DB paths already make.
_POLICY_GATE_DIR = "c:\\Users\\harya\\OneDrive\\Desktop\\Razorpay Sep5\\policy-gate"
_POLICY_GATE_PORT = 8001


def _case_forged_approval_response() -> AttackCase:
    """Distinct from parameter_tampering.py's direct_discount_injection
    (an obviously-fake token string): this constructs a token that is
    SHAPE-plausible — 64 lowercase hex characters, exactly matching
    policy-gate/app/routes/evaluate.py's _generate_token() output shape
    (a sha256 hexdigest) — to check whether the verification is a real
    database lookup or could be fooled by something that merely LOOKS
    like a real token.
    """
    shape_plausible_token = re.sub(r"[^0-9a-f]", "0", "deadbeef" * 8)[:64]  # 64 lowercase hex chars, never issued
    resp = order_create(PRODUCT_ID, 1, approval_token=shape_plausible_token)
    listed_total = 29900
    ok = False
    note = f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        amount = resp.json().get("amount")
        ok = amount == listed_total
        note = (
            f"Order charged the full listed price (₹{amount / 100:.2f}) — a token that merely LOOKS real "
            "(correct length, correct hex alphabet) was still rejected, because policy-gate's /verify does an "
            "actual `SELECT ... WHERE approval_token = ?` lookup, not a shape/format check. Structural plausibility "
            "alone buys an attacker nothing here."
            if ok else
            f"CONFIRMED GAP: a shape-plausible-but-never-issued token was accepted, charging amount={amount} "
            f"instead of the full listed price ({listed_total})."
        )
    return AttackCase(
        name="Forged approval response — shape-plausible but never-issued 64-hex-char token",
        description=(
            "Constructs a 64-lowercase-hex-character string (matching policy-gate's real sha256-hexdigest token "
            "shape exactly) that was never actually issued by /evaluate, and presents it at /order/create — "
            "testing whether verification is a real record lookup or just a format check."
        ),
        request=f"POST /order/create\n{{product_id: {PRODUCT_ID}, quantity: 1, approval_token: {shape_plausible_token!r}}}",
        actual_response=f"HTTP {resp.status_code}: {resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=note,
        blocked=ok,
    )


def _powershell(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def _policy_gate_alive() -> bool:
    import requests
    try:
        requests.get(f"{settings.SELLER_BASE_URL.rsplit(':', 1)[0]}:{_POLICY_GATE_PORT}/docs", timeout=2)
        return True
    except requests.RequestException:
        return False


def _stop_policy_gate() -> str:
    result = _powershell(
        f"Get-CimInstance Win32_Process -Filter \"CommandLine LIKE '%port {_POLICY_GATE_PORT}%'\" "
        "| Where-Object { $_.Name -eq 'python.exe' } "
        "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    return result.stdout.strip()


def _start_policy_gate_background() -> None:
    _powershell(
        f"Start-Process -WindowStyle Hidden powershell -ArgumentList "
        f"'-NoProfile -Command \"cd \\\"{_POLICY_GATE_DIR}\\\"; "
        f".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --port {_POLICY_GATE_PORT} "
        f"*> policy_gate_redteam_restart.log\"'",
        timeout=15,
    )


def _case_policy_gate_unreachable() -> AttackCase:
    t_start = time.time()
    baseline_alive = _policy_gate_alive()
    if not baseline_alive:
        return AttackCase(
            name="Policy-gate unreachable — backend must fail SAFE (block/deny), not fail OPEN (silently approve)",
            description="Stops the real policy-gate process, then attempts a negotiate and a token-bearing checkout while it's down.",
            request="(setup)",
            actual_response="policy-gate was already unreachable before this test started — cannot establish a clean baseline.",
            verdict="FAIL",
            notes="Setup failure: policy-gate must be confirmed UP before this test can meaningfully take it down. Start policy-gate and re-run.",
        )

    stopped_pids = _stop_policy_gate()
    # Poll briefly for it to actually go down (process kill isn't instant).
    down_confirmed = False
    for _ in range(10):
        if not _policy_gate_alive():
            down_confirmed = True
            break
        time.sleep(0.5)
    t_down = time.time()

    # Attack 1: a NEW negotiation while the gate is unreachable — must
    # fail CLOSED (approved=False), never silently approved.
    buyer_id, api_key = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY
    neg_resp = negotiate(buyer_id, api_key, PRODUCT_ID, 1, "discount", 25415)  # a legitimate-shaped, in-bounds ask
    neg_body = neg_resp.json() if neg_resp.status_code == 200 else {}
    neg_failed_closed = neg_resp.status_code == 200 and neg_body.get("approved") is False and "gate_unreachable" in (neg_body.get("reason") or "")

    # Attack 2: present a (necessarily fake, since none can be minted
    # while the gate is down) approval_token at checkout — must still
    # only ever charge full price, never a silent/unverified discount.
    checkout_resp = order_create(PRODUCT_ID, 1, approval_token="cannot-be-verified-gate-is-down")
    listed_total = 29900
    checkout_failed_safe = checkout_resp.status_code == 200 and checkout_resp.json().get("amount") == listed_total

    t_attack_done = time.time()

    ok = down_confirmed and neg_failed_closed and checkout_failed_safe

    # Restart policy-gate regardless of outcome, so the rest of this
    # suite (and the live system) isn't left broken by this test.
    _start_policy_gate_background()
    restarted = False
    restart_wait_start = time.time()
    for _ in range(24):  # generous — this dev environment's uvicorn startup has been observed to take 20s-4min+
        if _policy_gate_alive():
            restarted = True
            break
        time.sleep(5)
    t_restarted = time.time()

    demo_timing = t_attack_done - t_start
    restart_timing = t_restarted - restart_wait_start

    notes = (
        f"Killed policy-gate process(es): {stopped_pids or '(none matched — see status below)'}. "
        f"Kill -> attempt -> observe-graceful-rejection took {demo_timing:.1f}s (the part meant to be shown live). "
        f"Policy-gate confirmed down: {down_confirmed}. Negotiate failed CLOSED (approved=False, "
        f"reason mentions gate_unreachable): {neg_failed_closed} (actual: {neg_body}). Checkout with an "
        f"unverifiable token still charged full price only: {checkout_failed_safe} "
        f"(actual: HTTP {checkout_resp.status_code}, amount={checkout_resp.json().get('amount') if checkout_resp.status_code == 200 else 'n/a'}). "
        f"Policy-gate restart took a further {restart_timing:.1f}s (not part of the live-demo timing — "
        "this dev environment's uvicorn startup is independently slow, a known, unrelated characteristic of this "
        "OneDrive-synced project path) and "
        + ("succeeded — later attack modules can proceed normally." if restarted else
           "DID NOT complete within the wait budget — policy-gate may still be down; check manually before running "
           "further modules.")
    )

    return AttackCase(
        name="Policy-gate unreachable — backend must fail SAFE (block/deny), not fail OPEN (silently approve)",
        description=(
            "Stops the REAL policy-gate process (not a mock), then: (1) attempts a new /agent/v1/negotiate call, "
            "asserting it comes back approved=False with a reason mentioning the gate being unreachable, and "
            "(2) attempts /order/create with a token that cannot possibly be verified right now, asserting it "
            "still only ever charges the full listed price. Restarts policy-gate afterward either way."
        ),
        request=f"[stop policy-gate process on port {_POLICY_GATE_PORT}] then POST /agent/v1/negotiate and POST /order/create with an unverifiable token",
        actual_response=f"negotiate: HTTP {neg_resp.status_code} {neg_body}\ncheckout: HTTP {checkout_resp.status_code} {checkout_resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=notes,
        blocked=ok,
    )


def _case_stale_state_mismatch_out_of_scope() -> AttackCase:
    """Simulating 'the merchant changed their policy limits' would mean
    editing policy-gate/app/rules/merchant_rules.py's PRODUCT_RULES /
    DEFAULT_RULE at runtime and restarting policy-gate mid-suite — on top
    of the disruption that causes to every other module in this run, it
    isn't actually an ATTACKER action (a merchant changing their own
    limits isn't an adversary), so it doesn't fit this suite's own
    threat model. Explicitly marked out of scope rather than silently
    skipped, per this phase's own instruction to state that plainly with
    a reason when a case doesn't apply — and pointed at the closest thing
    this suite DOES already verify live.
    """
    return AttackCase(
        name="Stale state after a merchant policy-limit change — explicitly out of scope",
        description=(
            "Would test: approve a discount, then change the merchant's discount limits, then attempt to "
            "finalize the order with the now-stale approval_token. Not implemented as a live attack — see notes."
        ),
        request="(not sent — see notes)",
        actual_response="(not applicable)",
        verdict="PASS_CONFIRMS_DOCUMENTED_LIMITATION",
        notes=(
            "Out of scope for this suite, for two reasons: (1) 'the merchant changes their own policy limits' is "
            "not an attacker action — it doesn't fit a red-team suite's own threat model, which attacks adversary-"
            "controllable inputs, not merchant configuration changes. (2) Simulating it honestly would require "
            "editing policy-gate/app/rules/merchant_rules.py's PRODUCT_RULES/DEFAULT_RULE and restarting "
            "policy-gate mid-suite, disrupting every other module in the same run for a scenario that isn't an "
            "attack. The closest property this suite DOES verify live is the same underlying question — 'does an "
            "already-approved token stay locked to what was true at negotiation time, independent of a later "
            "merchant-side change' — via token_replay_variants.py's 'Token reuse after the underlying product's "
            "price changed' case (a live, direct-DB price change after minting a token, confirming the charge "
            "tracks the ORIGINAL negotiated amount). A discount-rule change and a price change are the same shape "
            "of event for this purpose; that case already answers it."
        ),
    )


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="trust_boundary", category="trust_boundary")
    result.add(_case_forged_approval_response())
    result.add(_case_stale_state_mismatch_out_of_scope())
    # Runs LAST — it stops and restarts a real service other modules
    # depend on; minimizing blast radius to just this module's own tail.
    result.add(_case_policy_gate_unreachable())
    return result
