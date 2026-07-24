"""Add User.language, VpnClient.public_token, Payment.subscription_id

Revision ID: 0003_lang_and_public_token
Revises: 0002_vpn_server_protocol
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_lang_and_public_token"
down_revision = "0002_vpn_server_protocol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("language", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "vpn_clients",
        sa.Column("public_token", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_vpnclient_public_token", "vpn_clients", ["public_token"]
    )
    op.create_index(
        "ix_vpnclient_public_token", "vpn_clients", ["public_token"]
    )
    op.add_column(
        "payments",
        sa.Column("subscription_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payment_subscription", "payments", "subscriptions",
        ["subscription_id"], ["id"],
    )
    op.create_index(
        "ix_payment_subscription_id", "payments", ["subscription_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_payment_subscription_id", table_name="payments")
    op.drop_constraint("fk_payment_subscription", "payments", type_="foreignkey")
    op.drop_column("payments", "subscription_id")
    op.drop_index("ix_vpnclient_public_token", table_name="vpn_clients")
    op.drop_constraint("uq_vpnclient_public_token", "vpn_clients", type_="unique")
    op.drop_column("vpn_clients", "public_token")
    op.drop_column("users", "language")
