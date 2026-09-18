from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def normalize_database_url(url: str) -> str:
    """Render (and most managed Postgres hosts) hand out a DATABASE_URL
    using the bare `postgres://` scheme — a legacy alias psycopg2 accepted
    but SQLAlchemy 2.0 + psycopg3 (this project's driver) does not; it
    needs the explicit `postgresql+psycopg://` dialect+driver prefix.
    `postgresql://` (no driver) is also rewritten so the driver is always
    explicit rather than SQLAlchemy silently picking whatever psycopg
    version happens to be installed. Anything else (sqlite:///...) passes
    through untouched.
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
    """Compatibility migrations for old local SQLite databases.

    New deployments should use Alembic. These lightweight ALTERs are kept so
    existing demo databases continue to boot after the hardening pass.
    """
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "orders" in table_names:
        existing_columns = {col["name"] for col in inspector.get_columns("orders")}
        order_columns = {
            "channel": "VARCHAR NOT NULL DEFAULT 'human'",
            "buyer_agent_id": "VARCHAR",
            "idempotency_key": "VARCHAR",
            # Commerce-platform pass: customer identity, quantity, price
            # snapshot, approval reference, payment time, fulfillment.
            "user_id": "VARCHAR",
            "user_email": "VARCHAR",
            "quantity": "INTEGER NOT NULL DEFAULT 1",
            "unit_price": "INTEGER",
            "approval_id": "INTEGER",
            "paid_at": "TIMESTAMP",
            "fulfillment_status": "VARCHAR",
        }
        with engine.begin() as conn:
            for col_name, col_type in order_columns.items():
                if col_name not in existing_columns:
                    conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col_name} {col_type}"))

    if "products" in table_names:
        existing_columns = {col["name"] for col in inspector.get_columns("products")}
        bool_default = "BOOLEAN NOT NULL DEFAULT true" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 1"
        product_columns = {
            "category": "VARCHAR",
            "detail_description": "VARCHAR",
            "image_urls": "JSON",
            "rating": "FLOAT",
            "review_count": "INTEGER",
            "negotiable": bool_default,
            "reviews": "JSON",
            "is_active": bool_default,
            "updated_at": "TIMESTAMP",
        }
        with engine.begin() as conn:
            for col_name, col_type in product_columns.items():
                if col_name not in existing_columns:
                    conn.execute(text(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}"))