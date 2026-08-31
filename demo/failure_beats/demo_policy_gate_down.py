"""Phase 14, demo beat 2 — "policy gate goes down, the system fails safe,
then recovers cleanly."

Standalone, one-command, HTTP-only (own venv, no imports from backend
source). Actually stops the REAL policy-gate process (Windows-specific,
via subprocess + PowerShell — the same commands used manually throughout
this project's dev sessions) — not a mock — because "does this fail
safe" can only be honestly answered by taking the real dependency down.

What this system ACTUALLY does when the gate is unreachable (by design,
established since Phase 3, and worth stating plainly rather than
overselling): a DISCOUNT can never be honored without the gate's live
approval — that half is what "blocked" means here. Checkout WITHOUT a
discount claim keeps working the entire time (full listed price only) —
that is this system's own long-standing "a bad/unverifiable token falls
back to full price, never a crash" behavior, not a workaround added for
this demo. Both halves are shown, narrated as what they actually are.

Run: python demo_policy_gate_down.py [--base-url http://127.0.0.1:8010] [--policy-gate-port 8001] [--policy-gate-dir <path>]
"""

import argparse
import subprocess
import sys
import time
import uuid

import httpx

DEFAULT_POLICY_GATE_DIR = "c:\\Users\\harya\\OneDrive\\Desktop\\Razorpay Sep5\\policy-gate"


def _step(n: int, total: int, message: str) -> None:
    print(f"[{n}/{total}] {message}")


def _powershell(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def _policy_gate_alive(client: httpx.Client, port: int) -> bool:
    try:
        client.get(f"http://127.0.0.1:{port}/docs", timeout=2)
        return True
    except httpx.HTTPError:
        return False


def _stop_policy_gate(port: int) -> str:
    result = _powershell(
        f"Get-CimInstance Win32_Process -Filter \"CommandLine LIKE '%port {port}%'\" "
        "| Where-Object { $_.Name -eq 'python.exe' } "
        "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    return result.stdout.strip()


def _start_policy_gate_background(policy_gate_dir: str, port: int) -> None:
    _powershell(
        f"Start-Process -WindowStyle Hidden powershell -ArgumentList "
        f"'-NoProfile -Command \"cd \\\"{policy_gate_dir}\\\"; "
        f".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --port {port} "
        f"*> policy_gate_demo_restart.log\"'",
        timeout=15,
    )


def _buy_a_discounted_unit(client: httpx.Client, base: str, product: dict) -> tuple[str, dict]:
    """Registers a fresh buyer, negotiates a real (legitimate, in-bounds)
    discount, and returns (buyer_id, negotiate_response) — used both
    before the outage (to show a discount CAN be earned while the gate is
    up) and after restart (to show it can be earned again).
    """
    buyer_id = f"demo-gatedown-{uuid.uuid4().hex[:8]}"
    resp = client.post(f"{base}/agent/v1/register", json={"buyer_agent_id": buyer_id})
    resp.raise_for_status()
    api_key = resp.json()["api_key"]
    headers = {"Authorization": f"Bearer {api_key}"}

    modest_discount_value = round(product["price"] * 0.92)  # 8% off — comfortably within any product's cap
    neg = client.post(
        f"{base}/agent/v1/negotiate",
        headers=headers,
        json={
            "product_id": product["id"],
            "quantity": 1,
            "buyer_agent_id": buyer_id,
            "proposed_terms": {"type": "discount", "value": modest_discount_value},
        },
    )
    neg.raise_for_status()
    return buyer_id, neg.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo: policy-gate outage fails safe, then recovers")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--policy-gate-port", type=int, default=8001)
    parser.add_argument("--policy-gate-dir", default=DEFAULT_POLICY_GATE_DIR)
    args = parser.parse_args()
    base = args.base_url
    port = args.policy_gate_port

    total_steps = 8
    t0 = time.time()

    with httpx.Client(timeout=15) as client:
        _step(1, total_steps, "Confirming policy-gate is UP before we touch anything...")
        if not _policy_gate_alive(client, port):
            print("    Policy-gate is already down — start it first so this demo has a clean baseline to break.")
            return 1
        print("    policy-gate: UP")

        _step(2, total_steps, f"Stopping the REAL policy-gate process (port {port}) — not a mock...")
        stopped = _stop_policy_gate(port)
        down_confirmed = False
        for _ in range(10):
            if not _policy_gate_alive(client, port):
                down_confirmed = True
                break
            time.sleep(0.5)
        print(f"    killed process(es): {stopped or '(none matched)'}  |  confirmed down: {down_confirmed}")
        t_demo_start = time.time()  # the "under 15s" clock starts here — setup/teardown don't count against it

        _step(3, total_steps, "Attempting a NEW negotiation (which needs a live gate decision) while it's down...")
        catalog = client.get(f"{base}/agent/v1/catalog").json()
        product = catalog[0]
        buyer_id, neg_body = _buy_a_discounted_unit(client, base, product)
        gate_blocked = neg_body.get("approved") is False and neg_body.get("reason") == "policy_gate_unreachable"
        print(f"    approved = {neg_body.get('approved')}, reason = {neg_body.get('reason')!r}")

        _step(4, total_steps, "Checking this shows up as a CLEAR message, not a generic error...")
        activity = client.get(f"{base}/dashboard/agent-activity", params={"limit": 10}).json()
        headline = None
        for group in activity:
            if group.get("buyer_agent_id") == buyer_id:
                headline = group.get("headline")
                break
        print(f"    dashboard headline: {headline!r}")
        clear_message_shown = bool(headline and "policy_gate_unreachable" in headline)

        _step(5, total_steps, "Confirming checkout WITHOUT a discount claim still safely works (full price only, never a crash)...")
        order_resp = client.post(
            f"{base}/order/create",
            json={"product_id": product["id"], "quantity": 1, "approval_token": None},
        )
        order_ok_at_full_price = order_resp.status_code == 200 and order_resp.json().get("amount") == product["price"]
        print(f"    order/create (no token) -> HTTP {order_resp.status_code}, amount = {order_resp.json().get('amount') if order_resp.status_code == 200 else order_resp.text}")

        demo_relevant_elapsed = time.time() - t_demo_start
        print(f"\n    >>> steps 3-5 (the live-demo portion) took {demo_relevant_elapsed:.1f}s <<<\n")

        _step(6, total_steps, "Restarting policy-gate (not part of the demo timing — recovery, shown for completeness)...")
        _start_policy_gate_background(args.policy_gate_dir, port)
        restarted = False
        restart_wait_start = time.time()
        for _ in range(30):
            if _policy_gate_alive(client, port):
                restarted = True
                break
            time.sleep(5)
        restart_seconds = time.time() - restart_wait_start
        print(f"    policy-gate back up: {restarted}  (took {restart_seconds:.1f}s — this dev environment's own uvicorn "
              f"startup latency, unrelated to the fix being demonstrated)")

        _step(7, total_steps, "Proving the block was resource-specific: the SAME discounted negotiation now succeeds...")
        if restarted:
            buyer_id_2, neg_body_2 = _buy_a_discounted_unit(client, base, product)
            recovery_ok = neg_body_2.get("approved") is True
            print(f"    approved = {neg_body_2.get('approved')}, final_terms = {neg_body_2.get('final_terms')}")
        else:
            recovery_ok = False
            print("    SKIPPED — policy-gate did not come back up in time; check it manually.")

        _step(8, total_steps, "Summary")
        all_ok = gate_blocked and clear_message_shown and order_ok_at_full_price and recovery_ok
        print(f"    Discount blocked while gate was down: {gate_blocked}")
        print(f"    Clear message on dashboard: {clear_message_shown}")
        print(f"    Checkout (no discount) kept working throughout: {order_ok_at_full_price}")
        print(f"    Clean recovery after restart: {recovery_ok}")

    total_elapsed = time.time() - t0
    print(f"\n=== DONE — total script runtime {total_elapsed:.1f}s (live-demo portion: {demo_relevant_elapsed:.1f}s) — "
          f"{'PASS' if all_ok else 'CHECK OUTPUT ABOVE'} ===\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
