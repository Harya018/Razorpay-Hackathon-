import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """This module has no code-level connection to the seller's backend or
    policy-gate — everything it knows about their HTTP interfaces comes
    from docs/agent-commerce-interface.md and the backend's own public
    route files, read the same way an external attacker would read them,
    never from importing backend/policy-gate code. Same independence rule
    buyer-agent and red-team-agent already follow; own venv, own .env,
    zero shared imports.
    """

    SELLER_BASE_URL: str = os.getenv("SELLER_BASE_URL", "http://127.0.0.1:8010")
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8010")

    # This suite registers its own fresh buyer-agent identity per run
    # (see attacks/concurrency.py's _register_attacker) rather than
    # relying on a pre-provisioned credential, so no API key needs to
    # live in this file.
    ATTACKER_ID_PREFIX: str = os.getenv("ATTACKER_ID_PREFIX", "redteam-async")

    # Used ONLY by attacks/replay.py to mint the single "captured" webhook
    # artifact those tests then replay — models an attacker who obtained
    # one genuine, validly-signed webhook delivery (compromised relay,
    # log leak, MITM), NOT an attacker who stole the merchant's secret for
    # arbitrary forgery. Same scoped exception red-team-agent's own
    # webhook_replay.py already documents.
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


settings = Settings()
