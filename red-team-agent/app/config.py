import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """This red-team agent has no code-level connection to the seller's
    backend or policy-gate — everything it knows about their HTTP
    interfaces comes from docs/agent-commerce-interface.md and this
    project's other public route files, read the same way an external
    attacker would read them, never from importing backend/policy-gate
    code. Same independence rule buyer-agent already follows.

    The SQLite paths below are the one deliberate exception: several
    attacks in this phase are explicitly about what happens when the
    application layer is bypassed entirely (direct DB writes), which by
    definition can't be done through an import — it's raw sqlite3
    against the same files those services use.
    """

    SELLER_BASE_URL: str = os.getenv("SELLER_BASE_URL", "http://127.0.0.1:8010")
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8010")

    ATTACKER_A_ID: str = os.getenv("ATTACKER_A_ID", "")
    ATTACKER_A_KEY: str = os.getenv("ATTACKER_A_KEY", "")
    ATTACKER_B_ID: str = os.getenv("ATTACKER_B_ID", "")
    ATTACKER_B_KEY: str = os.getenv("ATTACKER_B_KEY", "")

    BACKEND_DB_PATH: str = os.getenv("BACKEND_DB_PATH", "../backend/app.db")
    POLICY_GATE_DB_PATH: str = os.getenv("POLICY_GATE_DB_PATH", "../policy-gate/policy_gate.db")

    # Used ONLY by webhook_replay.py to mint the single "captured" webhook
    # artifact that test then replays — this models an attacker who
    # obtained one genuine, validly-signed webhook delivery (e.g. via a
    # compromised relay, log leak, or MITM), NOT an attacker who has
    # stolen the merchant's secret for arbitrary forgery. Same declared
    # exception as db_direct.py's direct-DB-access attacks: bypassing the
    # normal channel on purpose, for one specific, scoped reason.
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


settings = Settings()
