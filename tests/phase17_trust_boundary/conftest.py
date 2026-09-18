"""Phase 17 trust-boundary tests — shared fixtures and evidence logging.

Every test in this directory executes against the LIVE services (backend
:8010, policy-gate :8001, buyer-agent :8020) started the normal way
(`uvicorn ...`) — nothing here imports application code to test it
in-process. A test that can't reach a required live service is SKIPPED
(not silently passed) so a missing service never reads as "all green."

Evidence: every test writes its raw request/response payloads and
timestamps to evidence/<test_name>.json via the `evidence` fixture, and
results.md is generated from a full pytest run (see README at the bottom
of this file for the exact command).
"""

import json
import os
import time
from pathlib import Path

import pytest
import requests

BACKEND_URL = "http://127.0.0.1:8010"
POLICY_GATE_URL = "http://127.0.0.1:8001"
BUYER_AGENT_URL = "http://127.0.0.1:8020"


def _load_backend_env_value(key: str) -> str:
    """Reads one value straight out of backend/.env — the running
    backend process loads its own env the normal way (python-dotenv on
    import); this just lets a TEST independently know the same value
    (e.g. to mint a token signed with the same secret the server will
    verify it against), without importing backend application code into
    this suite's own process.
    """
    env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    # No backend/.env (CI, or a checkout configured purely via real env
    # vars) — read the same key from this process's own environment, which
    # CI sets identically for the backend job and this suite.
    return os.environ.get(key, "")


def mint_admin_token(email: str | None = None) -> str | None:
    """Mints a REAL, validly-signed (HS256) JWT using the same
    SUPABASE_JWT_SECRET the running backend verifies against — this
    exercises the actual signature-verification code path
    (backend/app/auth.py's require_user/require_merchant_admin), not a
    bypass of it. Returns None if no local SUPABASE_JWT_SECRET is
    configured (nothing to sign with) — callers should skip rather than
    fail in that case, since "auth isn't configured for local testing" is
    a different condition than "auth is broken."
    """
    try:
        import jwt
    except ImportError:
        return None

    secret = _load_backend_env_value("SUPABASE_JWT_SECRET")
    if not secret:
        return None

    admin_emails = _load_backend_env_value("MERCHANT_ADMIN_EMAILS")
    test_email = email or (admin_emails.split(",")[0].strip() if admin_emails else "test-merchant-admin@example.com")

    return jwt.encode(
        {"sub": "test-suite-admin", "email": test_email, "app_metadata": {"role": "MERCHANT_ADMIN"}, "exp": int(time.time()) + 3600},
        secret,
        algorithm="HS256",
    )

EVIDENCE_DIR = Path(__file__).parent / "evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)


def _require_live(url: str, name: str):
    try:
        requests.get(url, timeout=3)
    except requests.RequestException:
        pytest.skip(f"{name} is not reachable at {url} — start it before running this suite")


@pytest.fixture(scope="session", autouse=True)
def require_backend():
    _require_live(f"{BACKEND_URL}/docs", "backend")


@pytest.fixture(scope="session")
def require_policy_gate():
    _require_live(f"{POLICY_GATE_URL}/health", "policy-gate")


@pytest.fixture(scope="session")
def require_buyer_agent():
    _require_live(f"{BUYER_AGENT_URL}/docs", "buyer-agent")


class Evidence:
    """Accumulates {step_label: {...}} entries for one test and writes
    them to evidence/<test_id>.json on flush() — real request/response
    bodies and wall-clock timestamps, not a summary written after the
    fact from memory.
    """

    def __init__(self, test_id: str):
        self.test_id = test_id
        self.steps = []

    def record(self, label: str, **fields):
        entry = {"label": label, "ts": time.time(), "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())}
        entry.update(fields)
        self.steps.append(entry)
        return entry

    def flush(self, verdict: str, notes: str = ""):
        path = EVIDENCE_DIR / f"{self.test_id}.json"
        path.write_text(json.dumps({"test_id": self.test_id, "verdict": verdict, "notes": notes, "steps": self.steps}, indent=2, default=str))
        return path


@pytest.fixture
def evidence(request):
    ev = Evidence(request.node.name.replace("/", "_"))
    yield ev
    if not ev.steps:
        return
    # If the test didn't explicitly flush (e.g. it errored), flush with
    # whatever verdict pytest ultimately recorded for it.
    outcome = getattr(request.node, "_phase17_verdict", None)
    if outcome is None:
        rep = getattr(request.node, "rep_call", None)
        outcome = "PASS" if rep and rep.passed else ("FAIL" if rep and rep.failed else "UNKNOWN")
    ev.flush(outcome)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        setattr(item, "rep_call", rep)


def get_total_orders() -> int:
    """Phase 20 hardening made every /dashboard/* route merchant-admin-
    gated — several pre-existing tests in this suite use
    /dashboard/summary's total_orders purely as a convenient "did an
    order get created" oracle (not testing dashboard auth itself), so
    this centralizes the one auth header those call sites now need
    instead of repeating it everywhere.
    """
    token = mint_admin_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.get(f"{BACKEND_URL}/dashboard/summary", headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()["total_orders"]


def post(url, payload, **kwargs):
    return requests.post(url, json=payload, timeout=kwargs.pop("timeout", 30), **kwargs)


def get(url, **kwargs):
    return requests.get(url, timeout=kwargs.pop("timeout", 10), **kwargs)
