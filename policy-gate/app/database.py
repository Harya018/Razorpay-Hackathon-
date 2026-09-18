from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def normalize_database_url(url: str) -> str:
    """Render (and most managed Postgres hosts) hand out DATABASE_URL on
    the bare `postgres://` scheme, which SQLAlchemy 2.0 + psycopg3 no
    longer accepts without an explicit driver — rewritten to
    `postgresql+psycopg://` here. sqlite:// URLs pass through untouched.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(normalize_database_url(settings.DATABASE_URL), connect_args=connect_args, pool_pre_ping=True)
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
    """Compatibility migration for old local SQLite policy-gate databases
    only — fresh deployments get `requester_id` from Alembic's initial
    migration directly. Kept so a pre-existing local demo DB (created
    before Alembic existed) still boots: `requester_id` was Phase 8's fix
    for a red-team-confirmed cross-buyer token-theft gap (see
    /red-team-agent/results/red_team_report.md, token_replay_variants) —
    without it, /verify had no way to check WHO is redeeming a token, only
    whether product_id and cart_quantity matched. Existing rows backfill
    to NULL, which /verify treats as "no requester binding recorded" —
    i.e. exactly the pre-fix behavior for approvals that predate it.
    """
    inspector = inspect(engine)
    if "approvals" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("approvals")}
        if "requester_id" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE approvals ADD COLUMN requester_id VARCHAR"))