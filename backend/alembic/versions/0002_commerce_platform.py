"""commerce platform: order identity/quantity/fulfillment, product soft-delete, customer profiles

Revision ID: 0002_commerce_platform
Revises: 0001_initial_backend
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_commerce_platform"
down_revision = "0001_initial_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("user_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("user_email", sa.String(), nullable=True))
        batch.add_column(sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("unit_price", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("approval_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("paid_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("fulfillment_status", sa.String(), nullable=True))
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])

    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.create_table(
        "customer_profiles",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("address_line", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("pincode", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("customer_profiles")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("is_active")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    with op.batch_alter_table("orders") as batch:
        for col in ("fulfillment_status", "paid_at", "approval_id", "unit_price", "quantity", "user_email", "user_id"):
            batch.drop_column(col)
