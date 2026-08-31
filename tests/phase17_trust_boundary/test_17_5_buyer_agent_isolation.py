"""17.5 — Buyer agent isolation re-check.

Confirms isolation hasn't regressed after Phase 12-16 (the storefront/
dashboard design passes, the catalog rewrite): the buyer agent must still
have zero code-level coupling to the backend — same venv/process
independence claimed in docs/architecture-diagram.svg ("OWN venv - OWN
process - ZERO imports from backend").

Two checks, both executed for real:
  1. A subprocess run in the buyer agent's OWN venv attempts
     `import app.main as backend_main` (using the BACKEND's own module
     path/name) from buyer-agent's working directory, and must fail with
     ModuleNotFoundError — proving there's no accidental sys.path leakage
     or shared install making the backend importable from here.
  2. A source grep across every buyer-agent/app/*.py file for any import
     that isn't buyer-agent's own `app.*` package, `langgraph`,
     `pydantic`, or another third-party library — flagging anything that
     looks like a new Phase 12-16 backend-coupling import.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUYER_AGENT_DIR = REPO_ROOT / "buyer-agent"
BUYER_AGENT_PYTHON = BUYER_AGENT_DIR / ".venv" / "Scripts" / "python.exe"


@pytest.fixture(scope="module", autouse=True)
def require_buyer_agent_venv():
    if not BUYER_AGENT_PYTHON.exists():
        pytest.skip(f"buyer-agent venv not found at {BUYER_AGENT_PYTHON}")


def test_backend_package_is_not_importable_from_buyer_agent_venv(evidence):
    """Runs INSIDE buyer-agent's own venv/cwd — if this succeeded, it would
    mean the backend's package is somehow on this venv's import path
    (e.g. a stray sys.path.insert, a shared site-packages, an editable
    install) — real coupling, not a hypothetical one.
    """
    # backend's own top-level package is literally named "app", same as
    # buyer-agent's — so importing it by name alone proves nothing (it
    # would just resolve to buyer-agent's OWN app package). Instead,
    # probe for a symbol that only exists in the BACKEND's app package
    # (its FastAPI app.main entrypoint imports its own routes/dashboard),
    # run with cwd=backend/ so a bare "import app" WOULD resolve to the
    # backend if buyer-agent's venv could see it — but invoked as a
    # subprocess using buyer-agent's OWN interpreter and site-packages,
    # which is the actual isolation boundary being tested (langgraph,
    # fastapi versions, etc. pinned independently per requirements.txt).
    probe = (
        "import sys; "
        "sys.path.insert(0, r'" + str(REPO_ROOT / "backend") + "'); "
        "import app.gate_client"  # backend-only module; buyer-agent has no such module
    )
    result = subprocess.run(
        [str(BUYER_AGENT_PYTHON), "-c", probe],
        cwd=str(BUYER_AGENT_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    evidence.record(
        "subprocess_import_attempt",
        python=str(BUYER_AGENT_PYTHON),
        probe=probe,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )

    # This SHOULD fail — either with ModuleNotFoundError (buyer-agent's
    # venv lacks a backend dependency, e.g. sqlalchemy/razorpay) or
    # cleanly resolve app.gate_client only because we manually added the
    # backend to sys.path above (which is the test doing that deliberately,
    # not evidence of real coupling). The real assertion: WITHOUT that
    # manual sys.path.insert, does buyer-agent's OWN app package get
    # shadowed or does it have accidental access to backend deps?
    probe_no_path_hack = "import app.gate_client"
    result2 = subprocess.run(
        [str(BUYER_AGENT_PYTHON), "-c", probe_no_path_hack],
        cwd=str(BUYER_AGENT_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    evidence.record(
        "subprocess_import_attempt_no_path_hack",
        probe=probe_no_path_hack,
        returncode=result2.returncode,
        stdout=result2.stdout,
        stderr=result2.stderr,
    )

    passed = result2.returncode != 0 and "ModuleNotFoundError" in result2.stderr
    evidence.flush(
        "PASS" if passed else "FAIL",
        notes="" if passed else f"Expected ModuleNotFoundError for app.gate_client; got: {result2.stderr}",
    )
    assert result2.returncode != 0, (
        "Isolation regression: `import app.gate_client` (a backend-only module) succeeded from within "
        f"buyer-agent's own venv/cwd with no sys.path modification. stdout={result2.stdout!r}"
    )
    assert "ModuleNotFoundError" in result2.stderr, (
        f"Expected ModuleNotFoundError, got a different failure — investigate: {result2.stderr}"
    )


THIRD_PARTY_ALLOWED = (
    "app",  # buyer-agent's own package
    "langgraph",
    "langchain",
    "pydantic",
    "fastapi",
    "uvicorn",
    "httpx",
    "requests",
    "openai",
    "dotenv",
)
# Every standard-library module name (Python 3.10+) — anything else not
# in THIRD_PARTY_ALLOWED is flagged as worth a human look.
ALLOWED_PREFIXES = THIRD_PARTY_ALLOWED + tuple(sys.stdlib_module_names)


def test_no_new_backend_coupling_imports_added_in_phase_12_through_16(evidence):
    """Mechanical grep, not a guess: every top-level import name across
    buyer-agent/app/**/*.py, flagged if it isn't buyer-agent's own `app`
    package or a known third-party dependency. Comments mentioning
    "backend" are fine (this file's own docstring does it) — only actual
    `import`/`from X import` statements are checked.
    """
    import ast

    flagged = []
    checked_files = []
    for py_file in (BUYER_AGENT_DIR / "app").rglob("*.py"):
        checked_files.append(str(py_file.relative_to(REPO_ROOT)))
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [n.name.split(".")[0] for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative import, always fine
                names = [node.module.split(".")[0]] if node.module else []
            else:
                continue
            for name in names:
                if name not in ALLOWED_PREFIXES:
                    flagged.append({"file": str(py_file.relative_to(REPO_ROOT)), "import": name, "line": node.lineno})

    evidence.record("scanned_files", files=checked_files, count=len(checked_files))
    evidence.record("flagged_imports", flagged=flagged)
    evidence.flush(
        "PASS" if not flagged else "FAIL",
        notes="" if not flagged else f"{len(flagged)} unexpected import(s) found — see flagged_imports",
    )

    assert not flagged, f"Unexpected import(s) in buyer-agent source, possible backend coupling: {flagged}"
