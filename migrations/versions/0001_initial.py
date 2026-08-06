"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("is_banned", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_stars", sa.Integer(), nullable=False),
        sa.Column("price_usdt", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "vpn_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("api_key", sa.String(512), nullable=False),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("weight", sa.Integer(), default=100),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", "maintenance", name="vpnserverstatus"),
            default="active",
        ),
        sa.Column("max_clients", sa.Integer(), default=500),
        sa.Column("current_clients", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "failed", name="orderstatus"),
            default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("stars", "usdt", name="paymentprovider"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "paid", "failed", "refunded", name="paymentstatus"),
            default="pending",
        ),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "external_id", name="uq_payment_provider_external"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payment_external_id", "payments", ["external_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("vpn_servers.id"), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending_payment",
                "pending_provisioning",
                "active",
                "expired",
                "disabled",
                "error",
                name="subscriptionstatus",
            ),
            default="pending_payment",
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_extended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    op.create_table(
        "vpn_clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscriptions.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("vpn_servers.id"), nullable=False),
        sa.Column("amnezia_client_id", sa.String(512), nullable=False),
        sa.Column("client_name", sa.String(256), nullable=False),
        sa.Column("config_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", "deleted", name="vpnclientstatus"),
            default="active",
        ),
        sa.Column("protocol", sa.String(32), default="amneziawg"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "server_id", "amnezia_client_id", name="uq_vpnclient_server_client"
        ),
    )

    op.create_table(
        "processed_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(512), unique=True, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_processed_events_event_id", "processed_events", ["event_id"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "subscription_created",
                "subscription_renewed",
                "subscription_expired",
                "subscription_disabled",
                "subscription_enabled",
                "vpn_client_created",
                "vpn_client_disabled",
                "vpn_client_enabled",
                "vpn_client_deleted",
                "payment_received",
                "provisioning_failed",
                "provisioning_retried",
                name="auditaction",
            ),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("processed_events")
    op.drop_table("vpn_clients")
    op.drop_table("subscriptions")
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("vpn_servers")
    op.drop_table("plans")
    op.drop_table("users")
