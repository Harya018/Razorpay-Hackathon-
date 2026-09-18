"""initial backend schema

Revision ID: 0001_initial_backend
Revises:
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_backend"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("detail_description", sa.String(), nullable=True),
        sa.Column("image_urls", sa.JSON(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("negotiable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reviews", sa.JSON(), nullable=True),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"])
    op.create_index(op.f("ix_products_category"), "products", ["category"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("razorpay_order_id", sa.String(), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False, server_default="human"),
        sa.Column("buyer_agent_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_orders_id"), "orders", ["id"])
    op.create_index(op.f("ix_orders_razorpay_order_id"), "orders", ["razorpay_order_id"])
    op.create_index(op.f("ix_orders_buyer_agent_id"), "orders", ["buyer_agent_id"])
    op.create_index(op.f("ix_orders_idempotency_key"), "orders", ["idempotency_key"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("previous_hash", sa.String(), nullable=True),
        sa.Column("entry_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_audit_logs_id"), "audit_logs", ["id"])

    op.create_table(
        "buyer_agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("api_key_hash", sa.String(), nullable=False),
        sa.Column("spending_ceiling", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("buyer_agent_id"),
        sa.UniqueConstraint("api_key_hash"),
    )
    op.create_index(op.f("ix_buyer_agents_id"), "buyer_agents", ["id"])
    op.create_index(op.f("ix_buyer_agents_buyer_agent_id"), "buyer_agents", ["buyer_agent_id"])
    op.create_index(op.f("ix_buyer_agents_api_key_hash"), "buyer_agents", ["api_key_hash"])

    op.create_table(
        "purchase_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("terms_reference", sa.String(), nullable=False),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("declared_approval_token", sa.String(), nullable=True),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("terms_reference"),
    )
    op.create_index(op.f("ix_purchase_intents_id"), "purchase_intents", ["id"])
    op.create_index(op.f("ix_purchase_intents_terms_reference"), "purchase_intents", ["terms_reference"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
    )
    op.create_index(op.f("ix_idempotency_records_id"), "idempotency_records", ["id"])
    op.create_index(op.f("ix_idempotency_records_scope"), "idempotency_records", ["scope"])
    op.create_index(op.f("ix_idempotency_records_idempotency_key"), "idempotency_records", ["idempotency_key"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(op.f("ix_webhook_events_id"), "webhook_events", ["id"])
    op.create_index(op.f("ix_webhook_events_provider"), "webhook_events", ["provider"])
    op.create_index(op.f("ix_webhook_events_event_id"), "webhook_events", ["event_id"])


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("idempotency_records")
    op.drop_table("purchase_intents")
    op.drop_table("buyer_agents")
    op.drop_table("audit_logs")
    op.drop_table("orders")
    op.drop_table("products")