import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Loads configuration from environment variables. Never hardcode secrets here."""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    # The deployed frontend origin — used both as the CORS allowlist
    # default and wherever the backend needs to build a URL pointing back
    # at the app (e.g. an OAuth-adjacent redirect). CORS_ORIGINS may hold a
    # comma-separated list for multi-origin setups (e.g. a Vercel preview
    # URL alongside the production one) and defaults to just FRONTEND_URL.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", FRONTEND_URL)

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

    # Supabase Auth (human-facing identity only — never consulted by
    # policy-gate, never part of a discount/pricing decision). Backend
    # verifies the JWT itself (app/auth.py) rather than trusting any
    # frontend-supplied role. SUPABASE_JWT_SECRET (HS256, the project's
    # legacy JWT secret from Supabase's API settings) is the fast local
    # path; leave it blank to instead verify via Supabase's JWKS endpoint
    # (RS256/ES256, no shared secret needed — works for newer Supabase
    # projects using asymmetric signing keys). MERCHANT_ADMIN_EMAILS is a
    # comma-separated allowlist promoting specific Google-login emails to
    # MERCHANT_ADMIN when Supabase's own app_metadata.role isn't set up —
    # the simplest way to configure "who is Priya" for a demo without
    # needing a Supabase admin-role UI.
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    MERCHANT_ADMIN_EMAILS: str = os.getenv("MERCHANT_ADMIN_EMAILS", "")

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

    # Shared with policy-gate (its own GATE_SECRET env var — must be the
    # SAME value in both services' .env files). Policy-gate already uses
    # this to mint unforgeable approval tokens; this backend's only use of
    # it is as the X-Gate-Secret header on admin-only calls to policy-gate's
    # POST/PUT/DELETE /rules endpoints (app/routes/admin_rules.py) — the
    # ones that let a merchant adjust discount limits from the dashboard.
    # Those endpoints would otherwise be reachable by anyone who can reach
    # policy-gate's port; this is what makes them admin-only. Blank means
    # rule-adjustment calls fail (503), same fail-closed default as an
    # unconfigured GATE_SECRET on policy-gate's own side.
    GATE_SECRET: str = os.getenv("GATE_SECRET", "")

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

    # DEMO_MODE (distinct from DEMO_FALLBACK_MODE above, which is scoped
    # narrowly to third-party-outage resilience): a broader presentation
    # flag consulted, alongside DEMO_FALLBACK_MODE, wherever the LLM
    # provider chain decides whether its final tier may be a deterministic
    # templated response instead of erroring out (see the
    # `settings.DEMO_FALLBACK_MODE or settings.DEMO_MODE` checks in
    # app/agent/nodes.py) — and gates POST /auth/demo-login
    # (app/routes/auth.py), a one-click sign-in for local demos with no
    # real Supabase/Google OAuth project configured. Exactly like
    # DEMO_FALLBACK_MODE, this NEVER touches pricing, discount approval,
    # or payment verification — those always run for real regardless of
    # this flag, and the demo-login token is still independently verified
    # by the same require_user()/require_merchant_admin() path a real
    # Supabase token goes through.
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "0") == "1"

    # Optional startup seed for hosts with no shell access (Render free
    # tier): when "true", app startup runs scripts/seed_catalog.py's own
    # seed() — but ONLY if the products table is empty. seed() is written
    # for a one-off manual run: it resets every product's stock/price to
    # the seed values and hard-deletes any product not in its list, so
    # running it unconditionally on every restart would wipe real stock
    # deductions, merchant edits, and merchant-created products. Guarding
    # on "catalog is empty" keeps it safe to leave enabled permanently.
    # A deliberate full re-seed remains the manual script run.
    SEED_CATALOG_ON_STARTUP: bool = os.getenv("SEED_CATALOG_ON_STARTUP", "false").strip().lower() in ("1", "true", "yes")

    @property
    def cors_origins(self) -> list[str]:
        values = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return values or ["http://localhost:5173"]

    @property
    def merchant_admin_emails(self) -> set[str]:
        return {email.strip().lower() for email in self.MERCHANT_ADMIN_EMAILS.split(",") if email.strip()}


settings = Settings()