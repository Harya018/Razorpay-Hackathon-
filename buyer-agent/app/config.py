import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Loads configuration from environment variables. Never hardcode secrets here.

    This buyer agent has no code-level connection to the seller's
    backend — everything it knows about the seller comes from
    SELLER_BASE_URL plus docs/agent-commerce-interface.md, read by a human
    (or by me, while building this) — never from importing backend code.
    """

    # 127.0.0.1, not "localhost": on this dev machine, Python's `requests`
    # resolving "localhost" tries IPv6 (::1) first, times out, then falls
    # back to IPv4 — a real, reproducible ~2 second penalty on every single
    # HTTP call (confirmed live: localhost ~2.08s, 127.0.0.1 ~0.016s using
    # this exact venv's `requests`). The same bug was already found and
    # fixed on the backend's own POLICY_GATE_URL (see backend/app/config.py)
    # — this was the other, still-unfixed instance of it, found during the
    # Phase 18 cold-start audit: every register/catalog/negotiate/purchase/
    # pay call this agent has ever made to the seller paid this tax.
    SELLER_BASE_URL: str = os.getenv("SELLER_BASE_URL", "http://127.0.0.1:8010")

    BUYER_AGENT_ID: str = os.getenv("BUYER_AGENT_ID", "")
    BUYER_API_KEY: str = os.getenv("BUYER_API_KEY", "")

    # Own LLM credentials — a separate account/key from the seller's, even
    # though it happens to be the same provider (Groq) for convenience.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # Optional fallback tier, tried only if Groq is rate-limited — a
    # genuinely separate provider/quota pool. Blank skips this tier.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


settings = Settings()
