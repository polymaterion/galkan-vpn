"""
All SQLAlchemy ORM models.
Import order matters for Alembic to detect all tables.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SubscriptionStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    pending_provisioning = "pending_provisioning"
    active = "active"
    expired = "expired"
    disabled = "disabled"
    error = "error"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class PaymentProvider(str, enum.Enum):
    stars = "stars"
    usdt = "usdt"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class VpnServerStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    maintenance = "maintenance"


class VpnClientStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    deleted = "deleted"


class AuditAction(str, enum.Enum):
    subscription_created = "subscription_created"
    subscription_renewed = "subscription_renewed"
    subscription_expired = "subscription_expired"
    subscription_disabled = "subscription_disabled"
    subscription_enabled = "subscription_enabled"
    vpn_client_created = "vpn_client_created"
    vpn_client_disabled = "vpn_client_disabled"
    vpn_client_enabled = "vpn_client_enabled"
    vpn_client_deleted = "vpn_client_deleted"
    payment_received = "payment_received"
    provisioning_failed = "provisioning_failed"
    provisioning_retried = "provisioning_retried"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)     # XTR
    price_usdt: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="plan")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")


class VpnServer(Base, TimestampMixin):
    __tablename__ = "vpn_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key: Mapped[str] = mapped_column(String(512), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    weight: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[VpnServerStatus] = mapped_column(
        Enum(VpnServerStatus), default=VpnServerStatus.active
    )
    max_clients: Mapped[int] = mapped_column(Integer, default=500)
    current_clients: Mapped[int] = mapped_column(Integer, default=0)
    # Which amnezia-api protocol this server has installed/enabled:
    # "amneziawg", "amneziawg2" or "xray". Must match what's actually running
    # on that VPN server (check its amnezia-api .env: PROTOCOLS_ENABLED),
    # otherwise client creation fails with 400 Bad Request.
    protocol: Mapped[str] = mapped_column(String(32), default="amneziawg2")

    vpn_clients: Mapped[list["VpnClient"]] = relationship(back_populates="server")


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.pending, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="orders")
    plan: Mapped["Plan"] = relationship(back_populates="orders")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.pending
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="payments")
    order: Mapped["Order"] = relationship(back_populates="payments")

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_payment_provider_external"),
        Index("ix_payment_external_id", "external_id"),
    )


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    server_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vpn_servers.id"), nullable=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.pending_payment, nullable=False
    )
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_provisioned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_extended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship(back_populates="subscriptions")
    server: Mapped[Optional["VpnServer"]] = relationship()
    vpn_client: Mapped[Optional["VpnClient"]] = relationship(
        back_populates="subscription", uselist=False
    )


class VpnClient(Base, TimestampMixin):
    __tablename__ = "vpn_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"), unique=True, nullable=False
    )
    server_id: Mapped[int] = mapped_column(ForeignKey("vpn_servers.id"), nullable=False)
    amnezia_client_id: Mapped[str] = mapped_column(String(512), nullable=False)
    client_name: Mapped[str] = mapped_column(String(256), nullable=False)
    config_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # vpn:// URL
    status: Mapped[VpnClientStatus] = mapped_column(
        Enum(VpnClientStatus), default=VpnClientStatus.active
    )
    protocol: Mapped[str] = mapped_column(String(32), default="amneziawg")

    subscription: Mapped["Subscription"] = relationship(back_populates="vpn_client")
    server: Mapped["VpnServer"] = relationship(back_populates="vpn_clients")

    __table_args__ = (
        UniqueConstraint("server_id", "amnezia_client_id", name="uq_vpnclient_server_client"),
    )


class ProcessedEvent(Base):
    """Idempotency table – store processed payment event IDs to prevent double-processing."""
    __tablename__ = "processed_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
