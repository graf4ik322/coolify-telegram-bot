"""/deployments and /status handlers."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.formatting import format_app_card, fmt_deployment_status

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("status"))
async def cmd_status(message: Message, db_user: User, command: CommandObject) -> None:
    """Show application detail card.

    Usage: ``/status <app_name_or_uuid>``
    """
    arg = command.args
    if not arg:
        await message.answer("❌ Укажите имя или UUID приложения.\nПример: `/status my-app`")
        return

    try:
        # Try UUID first, then search by name
        try:
            app = await coolify.get_application(arg)
        except CoolifyClientError:
            apps = await coolify.list_applications()
            app = next((a for a in apps if a.name.lower() == arg.lower()), None)
            if not app:
                await message.answer(f"❌ Приложение «{arg}» не найдено.")
                return

        deploys = await coolify.list_deployments()
        latest = None
        for d in deploys:
            if d.application_uuid == app.uuid:
                latest = d
                break

        text = format_app_card(app, latest)
        await message.answer(text)
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка Coolify API: {exc.message}")
    except Exception:
        log.exception("Error in status command")
        await message.answer("❌ Не удалось получить статус приложения.")


@router.message(Command("deployments"))
async def cmd_deployments(message: Message, db_user: User) -> None:
    """List active/recent deployments."""
    try:
        deploys = await coolify.list_deployments()
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка Coolify API: {exc.message}")
        return
    except Exception:
        log.exception("Error listing deployments")
        await message.answer("❌ Не удалось получить список деплоев.")
        return

    if not deploys:
        await message.answer("📭 Нет активных деплоев.")
        return

    lines = ["📦 **Деплои:**\n"]
    for d in deploys:
        lines.append(fmt_deployment_status(d))
        lines.append("")

    await message.answer("\n".join(lines))
