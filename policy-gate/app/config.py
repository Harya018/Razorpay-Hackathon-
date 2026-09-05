import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Loads configuration from environment variables. Never hardcode secrets here."""

    # Genuinely separate from the backend's DB file — this service owns its
    # own data boundary, per the Level 2 decision on gate placement.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./policy_gate.db")

    # Used to mint approval_token — must never be derivable from data a
    # client already has, so this secret is what makes tokens unforgeable.
    GATE_SECRET: str = os.getenv("GATE_SECRET", "")

    # WHAT_BROKE.md #9 fix: /evaluate used to trust a caller-supplied
    # original_price with zero independent verification — a public,
    # unauthenticated endpoint accepting a fabricated price with no
    # catalog of its own to check it against. This is the one read-only
    # HTTP call back to the backend that closes that hole: /evaluate now
    # fetches the product's real price from here before trusting anything
    # the caller claims. Deliberately still HTTP-only, no shared DB, no
    # code import — same service-boundary principle as everywhere else in
    # this architecture, just now actually used for the one field that
    # trust boundary was silently exempting. 127.0.0.1, not localhost —
    # see README's "Known Gotchas" for why that distinction matters here.
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8010")


settings = Settings()
