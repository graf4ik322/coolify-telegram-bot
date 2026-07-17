"""/subscribe, /audit, /help handlers."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.db.models import User
from bot.db.repository import add_subscription, get_audit_logs, get_subscriptions, remove_subscription
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.formatting import fmt_relative_time

router = Router()
log = logging.getLogger(__name__)


# ── Subscribe ────────────────────────────────────────────────────────────────

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, db_user: User, command: CommandObject) -> None:
    """Subscribe to alerts for an application.

    Usage: ``/subscribe <app_name_or_uuid>``
    """
    arg = command.args
    if not arg:
        await message.answer("❌ Укажите имя или UUID приложения.\nПример: `/subscribe my-app`")
        return

    # Resolve app
    try:
        try:
            app = await coolify.get_application(arg)
        except CoolifyClientError:
            apps = await coolify.list_applications()
            app = next((a for a in apps if a.name.lower() == arg.lower()), None)
            if not app:
                await message.answer(f"❌ Приложение «{arg}» не найдено.")
                return
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка Coolify API: {exc.message}")
        return

    sub = await add_subscription(
        telegram_id=db_user.telegram_id,
        resource_uuid=app.uuid,
        resource_name=app.name,
    )
    if sub:
        await message.answer(
            f"✅ Подписка на алерты **{app.name}** оформлена.\n"
            "_Уведомления о сбоях будут приходить в этот чат._"
        )
    else:
        await message.answer(f"ℹ️ Вы уже подписаны на **{app.name}**.")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, db_user: User, command: CommandObject) -> None:
    """Unsubscribe from alerts.

    Usage: ``/unsubscribe <app_name_or_uuid>``
    """
    arg = command.args
    if not arg:
        await message.answer("❌ Укажите приложение.\nПример: `/unsubscribe my-app`")
        return

    # Resolve app
    try:
        try:
            app = await coolify.get_application(arg)
        except CoolifyClientError:
            apps = await coolify.list_applications()
            app = next((a for a in apps if a.name.lower() == arg.lower()), None)
            if not app:
                await message.answer(f"❌ Приложение «{arg}» не найдено.")
                return
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка Coolify API: {exc.message}")
        return

    ok = await remove_subscription(db_user.telegram_id, app.uuid)
    if ok:
        await message.answer(f"✅ Подписка на **{app.name}** отменена.")
    else:
        await message.answer(f"ℹ️ Вы не были подписаны на **{app.name}**.")


@router.message(Command("mysubs"))
async def cmd_mysubs(message: Message, db_user: User) -> None:
    """List your active subscriptions."""
    subs = await get_subscriptions(db_user.telegram_id)
    if not subs:
        await message.answer("📭 У вас нет активных подписок.\n`/subscribe <app>` для добавления.")
        return

    lines = ["🔔 **Ваши подписки:**\n"]
    for s in subs:
        lines.append(f"• **{s.resource_name}** ({s.resource_type})")
    await message.answer("\n".join(lines))


# ── Audit ────────────────────────────────────────────────────────────────────

@router.message(Command("audit"))
async def cmd_audit(message: Message, db_user: User) -> None:
    """Show recent audit log (Admin only)."""
    if db_user.role != "admin":
        await message.answer("❌ Команда доступна только администраторам.")
        return

    entries = await get_audit_logs(limit=20)
    if not entries:
        await message.answer("📭 Аудит-лог пуст.")
        return

    lines = ["📋 **Аудит-лог** (последние 20):\n"]
    for e in entries:
        status_icon = "✅" if e.status == "success" else "❌"
        when = fmt_relative_time(e.created_at.isoformat() if hasattr(e.created_at, 'isoformat') else str(e.created_at))
        action_label = f"{e.action.upper()} {e.resource_name or e.resource_uuid or ''}"
        lines.append(
            f"{status_icon} `{e.telegram_id}` {action_label}\n"
            f"   └ {when} {f'— {e.error_message}' if e.error_message else ''}"
        )

    await message.answer("\n".join(lines))


# ── Help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message, db_user: User) -> None:
    """Show help message."""
    role = db_user.role
    lines = [
        "📖 **Coolify Bot — Справка**\n",
        f"Ваша роль: **{role.upper()}**\n",
        "**Основные команды:**",
        "• `/apps` — список приложений (inline-карточки)",
        "• `/servers` — список серверов и health",
        "• `/status <app>` — карточка приложения",
        "• `/logs <app>` — логи приложения",
        "• `/deployments` — статусы деплоев",
        "• `/subscribe <app>` — подписка на алерты",
        "• `/unsubscribe <app>` — отписка",
        "• `/mysubs` — мои подписки",
        "",
    ]

    if role in ("operator", "admin"):
        lines.extend([
            "**Управление (inline-кнопки):**",
            "• Restart / Stop / Start приложения",
            "• Redeploy из текущего источника",
            "_Все действия требуют подтверждения (TTL 45 сек)_",
            "",
        ])

    if role == "admin":
        lines.extend([
            "**Админ-команды:**",
            "• `/audit` — просмотр аудит-лога действий",
        ])

    lines.extend([
        "",
        "💡 _Все операции управления — только через inline-кнопки,_",
        "_не как текстовые команды (защита от случайного ввода)._",
    ])

    await message.answer("\n".join(lines))
