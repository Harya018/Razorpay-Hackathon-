from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# check_same_thread is SQLite-specific connect_args, not SQLite-specific SQL —
# switching DATABASE_URL to Postgres later just drops this without touching models/queries.
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
    """Lightweight, idempotent "add column if missing" runner — this project
    has no Alembic setup (Base.metadata.create_all only creates NEW tables,
    it never alters existing ones), so a real schema change on an existing
    table needs this instead. Safe to call on every startup: existing rows
    keep their data, only missing columns get added with a default backfill.
    """
    inspector = inspect(engine)
    if "orders" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("orders")}
        if "channel" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN channel VARCHAR NOT NULL DEFAULT 'human'"))

    if "products" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("products")}
        # Phase 9 storefront columns — see app/models/product.py.
        product_columns = {
            "category": "VARCHAR",
            "detail_description": "VARCHAR",
            "image_urls": "JSON",
            "rating": "FLOAT",
            "review_count": "INTEGER",
            "negotiable": "BOOLEAN NOT NULL DEFAULT 1",
            "reviews": "JSON",
        }
        with engine.begin() as conn:
            for col_name, col_type in product_columns.items():
                if col_name not in existing_columns:
                    conn.execute(text(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}"))
