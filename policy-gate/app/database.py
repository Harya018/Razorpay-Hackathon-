from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Lightweight, idempotent "add column if missing" runner — same
    pattern as the backend's own database.py (see its docstring). Adds
    `requester_id` to `approvals`, Phase 8's fix for a red-team-confirmed
    cross-buyer token-theft gap (see /red-team-agent/results/
    red_team_report.md, token_replay_variants): without it, /verify had
    no way to check WHO is redeeming a token, only whether product_id and
    cart_quantity matched. Existing rows backfill to NULL, which /verify
    treats as "no requester binding recorded" — i.e. exactly today's
    behavior for every approval created before this migration ran.
    """
    inspector = inspect(engine)
    if "approvals" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("approvals")}
        if "requester_id" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE approvals ADD COLUMN requester_id VARCHAR"))
