"""Add User.trial_used, Plan.is_trial

Revision ID: 0004_trial
Revises: 0003_lang_and_public_token
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_trial"
down_revision = "0003_lang_and_public_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("trial_used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "plans",
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("plans", "is_trial")
    op.drop_column("users", "trial_used")
