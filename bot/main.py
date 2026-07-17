"""Coolify Telegram Bot — entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.db.repository import init_db
from bot.middleware.auth import AuthMiddleware
from bot.middleware.ratelimit import RateLimitMiddleware
from bot.router import register_routers
from bot.services.coolify import CoolifyClientError, coolify

log = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )


async def on_startup() -> None:
    """Initialise services on bot startup."""
    log.info("Starting Coolify Telegram Bot...")

    # Database
    await init_db()

    # Verify Coolify API connectivity
    try:
        health = await coolify.health()
        ver = await coolify.version()
        log.info("Coolify API: health=%s version=%s", health.status, ver)
    except Exception as exc:
        log.warning("Coolify API unreachable at startup: %s", exc)

    # Set up Telegram bot commands (non-fatal if fails)
    try:
        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
        commands = [
            BotCommand(command="start", description="🚀 Запуск и проверка доступа"),
            BotCommand(command="apps", description="📱 Список приложений"),
            BotCommand(command="projects", description="📋 Проекты и окружения"),
            BotCommand(command="servers", description="🖥 Список серверов"),
            BotCommand(command="status", description="📊 Карточка приложения"),
            BotCommand(command="logs", description="📋 Логи приложения"),
            BotCommand(command="deployments", description="📦 Статусы деплоев"),
            BotCommand(command="subscribe", description="🔔 Подписаться на алерты"),
            BotCommand(command="unsubscribe", description="🔕 Отписаться от алертов"),
            BotCommand(command="mysubs", description="📭 Мои подписки"),
            BotCommand(command="audit", description="📋 Аудит-лог (Admin)"),
            BotCommand(command="ping", description="🩺 Проверка здоровья бота"),
            BotCommand(command="help", description="📖 Справка"),
        ]
        await bot.set_my_commands(commands)
        await bot.close()
    except Exception as exc:
        log.warning("Bot command setup failed (non-fatal): %s", exc)
    finally:
        # Ensure aiohttp session is cleaned up even if close() fails
        if "bot" in dir():
            try:
                await bot.session.close()
            except Exception:
                pass

    log.info("Bot startup complete.")


async def on_shutdown() -> None:
    """Clean up on shutdown."""
    await coolify.close()
    log.info("Coolify Telegram Bot stopped.")


# ── Global callbacks ─────────────────────────────────────────────────────────

async def menu_main(cb: CallbackQuery) -> None:
    """Show main navigation menu."""
    text = (
        "🏠 **Главное меню**\n\n"
        "Выберите раздел:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Приложения", callback_data="menu:apps")],
        [InlineKeyboardButton(text="🖥 Серверы", callback_data="menu:servers")],
        [InlineKeyboardButton(text="📦 Деплои", callback_data="menu:deployments")],
        [InlineKeyboardButton(text="🔔 Подписки", callback_data="menu:subscriptions")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


async def main() -> None:
    """Main entry point."""
    setup_logging()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()

    # Startup / shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Middleware (order matters: auth before rate-limit)
    dp.update.middleware(AuthMiddleware())
    dp.update.middleware(RateLimitMiddleware())

    # Register routers
    register_routers(dp)

    # ── Inline callbacks ─────────────────────────────────────────────────

    @dp.callback_query(lambda c: c.data == "noop")
    async def noop(cb: CallbackQuery) -> None:
        await cb.answer()

    @dp.callback_query(lambda c: c.data == "menu:main")
    async def menu_main_handler(cb: CallbackQuery) -> None:
        await menu_main(cb)

    @dp.callback_query(lambda c: c.data.startswith("menu:"))
    async def menu_nav(cb: CallbackQuery) -> None:
        """Route menu selections to appropriate handlers."""
        target = cb.data.split(":", 1)[1]
        mapping = {
            "apps": "apps",
            "servers": "servers",
            "deployments": "deployments",
            "subscriptions": "mysubs",
            "help": "help",
        }
        if target in mapping:
            # Simulate command by editing message content
            # The actual handler will be called from the command
            await cb.answer(f"Используйте /{mapping[target]}")
        else:
            await cb.answer()

    @dp.callback_query(lambda c: c.data.startswith("page:"))
    async def page_nav(cb: CallbackQuery) -> None:
        """Handle pagination navigation with caching."""
        parts = cb.data.split(":", 2)
        if len(parts) < 3:
            await cb.answer()
            return
        prefix = parts[1]
        try:
            page = int(parts[2])
        except ValueError:
            await cb.answer()
            return

        try:
            # Use cached apps
            from bot.services.coolify import coolify

            apps = await coolify.list_applications()
        except CoolifyClientError as exc:
            await cb.message.edit_text(f"❌ Ошибка загрузки списка: {exc.message}")
            await cb.answer()
            return

        from bot.utils.formatting import format_app_short
        from bot.utils.pagination import Pagination

        pag = Pagination(items=apps, per_page=5, format_fn=format_app_short)
        kb = pag.build(page=page, callback_prefix=prefix)
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
        ])
        await cb.message.edit_text(
            f"📱 **Приложения** ({len(apps)} всего):\n_Выберите приложение для просмотра_",
            reply_markup=kb,
        )
        await cb.answer()

    try:
        log.info("Starting polling...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
