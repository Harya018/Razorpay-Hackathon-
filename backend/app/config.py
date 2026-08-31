import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Loads configuration from environment variables. Never hardcode secrets here."""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # Razorpay TEST mode keys only (rzp_test_...). Live keys must never be used in this codebase.
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    # Groq API key for the seller negotiation agent. Groq's API is
    # OpenAI-compatible — we use the `openai` SDK pointed at api.groq.com.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # Optional fallback key (a different Groq account) — used automatically
    # if GROQ_API_KEY hits its daily token quota mid-request. Blank means
    # no fallback is configured. Note: a second key on the SAME Groq
    # account shares that account's quota pool and won't actually help —
    # confirmed live when testing this (both keys hit an identical 429
    # from the same org_id). Only a key from a genuinely different Groq
    # account provides real headroom.
    GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # Gemini, via Google's OpenAI-compatible endpoint — a genuinely
    # separate provider/quota pool, used as the next fallback after both
    # Groq keys are exhausted. Blank means this fallback tier is skipped.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    # The policy-gate service — a separate process, called over HTTP only.
    # Never imported/called in-process; this URL is the entire coupling.
    # 127.0.0.1, not "localhost": on this dev machine, Python's `requests`
    # resolving "localhost" tries IPv6 (::1) first, times out (policy-gate/
    # uvicorn only binds IPv4 by default), then falls back to IPv4 — a
    # real, reproducible ~2 SECOND penalty on every single /evaluate and
    # /verify call, confirmed live (localhost: ~2.07s, 127.0.0.1: ~0.015s,
    # measured with `requests` directly). Found while building the
    # dashboard's Policy Gate Status latency panel — its honest number is
    # exactly what surfaced this.
    POLICY_GATE_URL: str = os.getenv("POLICY_GATE_URL", "http://127.0.0.1:8001")

    # Phase 11 — where redteam/ (a sibling project, its own venv, no code
    # coupling) writes its per-category JSON scorecard files
    # (concurrency/replay/injection/tampering/trust_results.json). The
    # dashboard's Security Posture panel only ever READS these files —
    # this backend never runs, imports, or triggers the red-team suite
    # itself. Relative to this project's dev layout (all services checked
    # out as siblings), same assumption redteam/'s own attack modules
    # already make in the other direction (HTTP-only, no imports back
    # into this backend). There's also an older, narrative-report suite
    # at red-team-agent/ (Phase 8/9) — this panel deliberately reads the
    # newer, structured redteam/ suite instead, since it's this project's
    # current five-category source of truth.
    RED_TEAM_RESULTS_DIR: str = os.getenv("RED_TEAM_RESULTS_DIR", "../redteam/results")

    # Phase 13 — where metrics/recovery_sim.py (a sibling project, its own
    # venv, HTTP-only, no code coupling) writes its revenue-recovery
    # simulation output. The dashboard's recovery-rate stat card only ever
    # READS this file; this backend never runs the simulation itself.
    RECOVERY_SIM_RESULTS_PATH: str = os.getenv("RECOVERY_SIM_RESULTS_PATH", "../metrics/results/recovery_sim.json")

    # Phase 18.5 — demo-day resilience against THIRD-PARTY flakiness
    # (Groq down/slow, Razorpay's test-mode endpoint down/slow, bad venue
    # wifi), as distinct from this project's OWN services failing (which
    # the existing fail-closed Policy Gate behavior + demo/failure_beats/
    # scripts already cover). OFF by default — never silently active.
    # When ON: (1) if EVERY configured LLM provider fails (not just
    # rate-limited — genuinely down/timed out), the seller agent's discount
    # offer falls back to a deterministic canned message built from the
    # SAME real ladder value an LLM would have framed, rather than aborting
    # the negotiation — the discount math is never fake, only the prose is
    # templated; (2) if the real Razorpay order.create() call fails, a
    # synthetic, clearly-labeled fallback order is used so checkout can
    # still complete for demo purposes. Every fallback use is written to
    # the audit log as its own event type — never indistinguishable from
    # the real thing. See README.md's "Known Gotchas" and
    # demo/failure_beats/ for how this is rehearsed before a live demo.
    DEMO_FALLBACK_MODE: bool = os.getenv("DEMO_FALLBACK_MODE", "0") == "1"


settings = Settings()
