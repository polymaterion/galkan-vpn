"""Add protocol column to vpn_servers

Revision ID: 0002_vpn_server_protocol
Revises: 0001_initial
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_vpn_server_protocol"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_servers",
        sa.Column(
            "protocol",
            sa.String(length=32),
            nullable=False,
            server_default="amneziawg2",
        ),
    )


def downgrade() -> None:
    op.drop_column("vpn_servers", "protocol")
