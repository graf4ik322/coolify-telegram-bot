"""/start handler — whitelist check and welcome."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.db.models import User
from bot.services.coolify import coolify

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    """Health-check command for the bot itself."""
    import time

    start = time.time()
    try:
        health = await coolify.health()
        coolify_ok = f"✅ {health.status}"
    except Exception:
        coolify_ok = "❌ недоступен"

    elapsed = int((time.time() - start) * 1000)
    await message.answer(
        f"🩺 **Bot Health**\n\n"
        f"🤖 Бот: ✅ работает\n"
        f"⚡ Ответ: `{elapsed}ms`\n"
        f"🔗 Coolify API: {coolify_ok}\n"
        f"🕐 Uptime: _запущен с начала сессии_"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    """Welcome message with inline main menu."""
    role_emoji = {"admin": "🛡️", "operator": "🔧", "viewer": "👁️"}
    emoji = role_emoji.get(db_user.role, "👤")

    text = (
        f"{emoji} **Coolify Bot** — {db_user.role.upper()}\n\n"
        f"_Приборная панель + рычаг перезапуска_"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Приложения", callback_data="menu:apps_go")],
        [InlineKeyboardButton(text="📋 Проекты", callback_data="menu:projects_go")],
        [InlineKeyboardButton(text="🖥 Серверы", callback_data="menu:servers_go")],
        [InlineKeyboardButton(text="📦 Деплои", callback_data="menu:deployments_go")],
        [InlineKeyboardButton(text="🔔 Подписки", callback_data="menu:subscriptions_go")],
        [InlineKeyboardButton(text="🩺 Здоровье", callback_data="menu:ping")],
        [InlineKeyboardButton(text="📖 Помощь", callback_data="menu:help")],
    ])

    await message.answer(text, reply_markup=kb)
