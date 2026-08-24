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


settings = Settings()
