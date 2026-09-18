"""add gate_config and product_rule_overrides (admin-editable Policy Gate rules)

Revision ID: 0002_gate_config
Revises: 0001_initial_policy_gate
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_gate_config"
down_revision = "0001_initial_policy_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gate_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("default_max_discount_pct", sa.Float(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "product_rule_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("max_discount_pct", sa.Float(), nullable=False),
        sa.Column("floor_price", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(op.f("ix_product_rule_overrides_product_id"), "product_rule_overrides", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_rule_overrides")
    op.drop_table("gate_config")
