"""/adduser command — admin-only user management."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import delete, select

from bot.db.models import User, User as UserModel
from bot.db.repository import get_session_factory, get_user, upsert_user

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("adduser"))
async def cmd_adduser(message: Message, db_user: User, command: CommandObject) -> None:
    """Add a user to whitelist. Admin only.

    Usage: ``/adduser <telegram_id> <role>``
    Roles: viewer | operator | admin
    """
    if db_user.role != "admin":
        await message.answer("❌ Команда доступна только администраторам.")
        return

    args = command.args
    if not args:
        await message.answer(
            "❌ Укажите Telegram ID и роль.\n"
            "Пример: `/adduser 123456789 operator`\n\n"
            "Роли: `viewer` (просмотр), `operator` (управление), `admin`"
        )
        return

    parts = args.split(None, 1)
    if len(parts) < 2:
        await message.answer("❌ Укажите роль.\nПример: `/adduser 123456789 operator`")
        return

    try:
        telegram_id = int(parts[0])
    except ValueError:
        await message.answer("❌ Telegram ID должен быть числом.\nПример: `/adduser 123456789 operator`")
        return

    role = parts[1].strip().lower()
    if role not in ("viewer", "operator", "admin"):
        await message.answer(
            "❌ Неверная роль. Допустимые: `viewer`, `operator`, `admin`"
        )
        return

    existing = await get_user(telegram_id)
    user = await upsert_user(telegram_id, role=role)

    if existing:
        await message.answer(
            f"✅ Пользователь `{telegram_id}` обновлён.\n"
            f"Роль: **{role.upper()}**"
        )
    else:
        await message.answer(
            f"✅ Пользователь `{telegram_id}` добавлен.\n"
            f"Роль: **{role.upper()}**\n\n"
            f"Теперь он может использовать `/start` для входа."
        )


@router.message(Command("deluser"))
async def cmd_deluser(message: Message, db_user: User, command: CommandObject) -> None:
    """Remove a user from whitelist. Admin only.

    Usage: ``/deluser <telegram_id>``
    """
    if db_user.role != "admin":
        await message.answer("❌ Команда доступна только администраторам.")
        return

    args = command.args
    if not args:
        await message.answer("❌ Укажите Telegram ID.\nПример: `/deluser 123456789`")
        return

    try:
        telegram_id = int(args.strip())
    except ValueError:
        await message.answer("❌ Telegram ID должен быть числом.")
        return

    user = await get_user(telegram_id)
    if not user:
        await message.answer(f"❌ Пользователь `{telegram_id}` не найден.")
        return

    async with get_session_factory() as session:
        await session.execute(
            delete(UserModel).where(UserModel.telegram_id == telegram_id)
        )
        await session.commit()

    await message.answer(f"✅ Пользователь `{telegram_id}` удалён.")


@router.message(Command("users"))
async def cmd_users(message: Message, db_user: User) -> None:
    """List all whitelisted users. Admin only."""
    if db_user.role != "admin":
        await message.answer("❌ Команда доступна только администраторам.")
        return

    async with get_session_factory() as session:
        result = await session.execute(
            select(UserModel).order_by(UserModel.created_at)
        )
        all_users = result.scalars().all()

    if not all_users:
        await message.answer("📭 Нет пользователей в whitelist.")
        return

    lines = ["👥 **Пользователи:**\n"]
    for u in all_users:
        role_emoji = {"admin": "🛡️", "operator": "🔧", "viewer": "👁️"}
        active = "✅" if u.is_active else "❌"
        lines.append(
            f"{active} {role_emoji.get(u.role, '👤')} `{u.telegram_id}` — **{u.role.upper()}**"
        )

    await message.answer("\n".join(lines))
