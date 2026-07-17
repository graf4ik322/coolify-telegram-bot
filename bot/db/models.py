"""Database models for Coolify Telegram Bot."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(sa.String(16), default="viewer")  # viewer | operator | admin
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resource_uuid: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    resource_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(sa.Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(sa.String(16), default="success")
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    resource_uuid: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    resource_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.String(32), default="application")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    __table_args__ = (
        sa.UniqueConstraint("telegram_id", "resource_uuid"),
    )
