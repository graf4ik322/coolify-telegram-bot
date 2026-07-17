"""/start handler — whitelist check and welcome."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db.models import User

router = Router()
log = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    """Welcome message for authorised users."""
    role_emoji = {"admin": "🛡️", "operator": "🔧", "viewer": "👁️"}
    emoji = role_emoji.get(db_user.role, "👤")

    await message.answer(
        f"{emoji} Привет, {message.from_user.full_name}!\n\n"
        f"**Coolify Telegram Bot** — приборная панель управления.\n"
        f"Ваша роль: **{db_user.role.upper()}**\n\n"
        "**Команды:**\n"
        "• `/apps` — список приложений и их статусы\n"
        "• `/servers` — список серверов и health\n"
        "• `/status <app>` — карточка приложения\n"
        "• `/logs <app>` — логи приложения\n"
        "• `/deployments` — активные деплои\n"
        "• `/subscribe <app>` — подписка на алерты\n"
        "• `/help` — полная справка\n\n"
        "_Операции Restart/Stop/Start — через inline-кнопки в карточке приложения._",
    )
