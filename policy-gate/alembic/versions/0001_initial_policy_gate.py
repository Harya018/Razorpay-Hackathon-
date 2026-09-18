"""initial policy gate schema

Revision ID: 0001_initial_policy_gate
Revises:
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_policy_gate"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("requester_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("cart_quantity", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("final_amount", sa.Integer(), nullable=True),
        sa.Column("approval_token", sa.String(), nullable=True),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("approval_token"),
    )
    op.create_index(op.f("ix_approvals_id"), "approvals", ["id"])
    op.create_index(op.f("ix_approvals_session_id"), "approvals", ["session_id"])
    op.create_index(op.f("ix_approvals_approval_token"), "approvals", ["approval_token"])


def downgrade() -> None:
    op.drop_table("approvals")