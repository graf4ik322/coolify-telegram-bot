"""Coolify Telegram Bot — entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db.repository import init_db
from bot.handlers import actions, apps, deploy, logs, servers, start, subscribe
from bot.middleware.auth import AuthMiddleware
from bot.middleware.ratelimit import RateLimitMiddleware
from bot.router import register_routers
from bot.services.coolify import coolify

log = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure structured (JSON-like) logging."""
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

    # Set up Telegram bot commands
    from aiogram.types import BotCommand

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    commands = [
        BotCommand(command="start", description="🚀 Запуск и проверка доступа"),
        BotCommand(command="apps", description="📱 Список приложений"),
        BotCommand(command="servers", description="🖥 Список серверов"),
        BotCommand(command="status", description="📊 Карточка приложения"),
        BotCommand(command="logs", description="📋 Логи приложения"),
        BotCommand(command="deployments", description="📦 Статусы деплоев"),
        BotCommand(command="subscribe", description="🔔 Подписаться на алерты"),
        BotCommand(command="unsubscribe", description="🔕 Отписаться от алертов"),
        BotCommand(command="mysubs", description="📭 Мои подписки"),
        BotCommand(command="audit", description="📋 Аудит-лог (Admin)"),
        BotCommand(command="help", description="📖 Справка"),
    ]
    await bot.set_my_commands(commands)
    await bot.close()

    log.info("Bot startup complete.")


async def on_shutdown() -> None:
    """Clean up on shutdown."""
    await coolify.close()
    log.info("Coolify Telegram Bot stopped.")


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

    # Also register route for pagination and generic callbacks
    from aiogram import F
    from aiogram.types import CallbackQuery

    @dp.callback_query(F.data == "noop")
    async def noop(cb: CallbackQuery) -> None:
        await cb.answer()

    @dp.callback_query(F.data.startswith("page:"))
    async def page_nav(cb: CallbackQuery) -> None:
        """Handle pagination navigation."""
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

        # Re-build paginated list
        from bot.services.coolify import coolify

        apps_list = await coolify.list_applications()
        from bot.utils.pagination import Pagination
        from bot.utils.formatting import format_app_short

        pag = Pagination(items=apps_list, per_page=5, format_fn=format_app_short)
        kb = pag.build(page=page, callback_prefix=prefix)
        total = len(apps_list)
        await cb.message.edit_text(
            f"📱 **Приложения** ({total} всего):\n_Выберите приложение для просмотра_",
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
