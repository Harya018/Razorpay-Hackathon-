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


settings = Settings()
