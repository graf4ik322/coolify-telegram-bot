"""Database repository — CRUD for users, audit, subscriptions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.db.models import AuditLog, Base, Subscription, User

log = logging.getLogger(__name__)


def _ensure_db_dir() -> None:
    """Create the database directory if it doesn't exist.

    Prevents 'unable to open database file' when SQLite tries to create
    the DB file in a non-existent directory.
    """
    # Parse path from sqlite+aiosqlite:///path/to/db
    raw = settings.database_url
    if raw.startswith("sqlite"):
        # Extract path after file:// or /// or :///
        path_part = raw.split("///", 1)[-1] if "///" in raw else raw.split("://", 1)[-1]
        if path_part and not path_part.startswith(":"):  # not in-memory
            db_dir = Path(path_part).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            log.info("Database directory ensured: %s", db_dir)


_ensure_db_dir()

_engine = create_async_engine(settings.database_url, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_session_factory():
    """Return the async session maker for external use."""
    return _session_factory


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Database tables created / verified.")


async def get_session() -> AsyncSession:
    """Yield an async session."""
    return _session_factory()


# ── Users ────────────────────────────────────────────────────────────────────

async def get_user(telegram_id: int) -> User | None:
    async with _session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()


async def upsert_user(telegram_id: int, role: str = "viewer") -> User:
    async with _session_factory() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.role = role
        else:
            user = User(telegram_id=telegram_id, role=role)
            session.add(user)
        await session.commit()
        return user


# ── Audit ────────────────────────────────────────────────────────────────────

async def log_action(
    telegram_id: int,
    action: str,
    resource_type: str,
    resource_uuid: str | None = None,
    resource_name: str | None = None,
    details: dict | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> AuditLog:
    async with _session_factory() as session:
        entry = AuditLog(
            telegram_id=telegram_id,
            action=action,
            resource_type=resource_type,
            resource_uuid=resource_uuid,
            resource_name=resource_name,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            status=status,
            error_message=error_message,
        )
        session.add(entry)
        await session.commit()
        return entry


async def get_audit_logs(limit: int = 20) -> list[AuditLog]:
    async with _session_factory() as session:
        result = await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


# ── Subscriptions ────────────────────────────────────────────────────────────

async def add_subscription(
    telegram_id: int,
    resource_uuid: str,
    resource_name: str,
    resource_type: str = "application",
) -> Subscription | None:
    async with _session_factory() as session:
        existing = await session.execute(
            select(Subscription).where(
                Subscription.telegram_id == telegram_id,
                Subscription.resource_uuid == resource_uuid,
            )
        )
        if existing.scalar_one_or_none():
            return None
        sub = Subscription(
            telegram_id=telegram_id,
            resource_uuid=resource_uuid,
            resource_name=resource_name,
            resource_type=resource_type,
        )
        session.add(sub)
        await session.commit()
        return sub


async def remove_subscription(telegram_id: int, resource_uuid: str) -> bool:
    async with _session_factory() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.telegram_id == telegram_id,
                Subscription.resource_uuid == resource_uuid,
                Subscription.is_active.is_(True),
            )
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return False
        sub.is_active = False
        await session.commit()
        return True


async def get_subscriptions(telegram_id: int) -> list[Subscription]:
    async with _session_factory() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.telegram_id == telegram_id,
                Subscription.is_active.is_(True),
            )
        )
        return list(result.scalars().all())
