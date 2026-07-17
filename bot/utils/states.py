"""State templates for consistent UI across all handlers.

Every screen has 5 possible states: loading, empty, error, partial, success.
States use single-message editing where possible.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Loading ──────────────────────────────────────────────────────────────────

def loading_text(action: str = "Загружаем") -> str:
    """Return loading message text."""
    return f"⏳ {action}..."


# ── Empty ────────────────────────────────────────────────────────────────────

EMPTY_STATES: dict[str, str] = {
    "projects": "📭 **Нет проектов**\n\nСоздайте первый проект в панели Coolify.",
    "apps": "📭 **Нет приложений**\n\nВ этом проекте/окружении пока нет приложений.",
    "servers": "📭 **Нет серверов**\n\nДобавьте сервер через панель Coolify.",
    "deployments": "📭 **Нет деплоев**\n\nИстория деплоев пуста.",
    "logs": "📭 **Логов пока нет**\n\nПриложение ещё не запускалось или логи не сгенерированы.",
    "subscriptions": "📭 **Нет подписок**\n\nИспользуйте `/subscribe <app>` для подписки на алерты.",
    "audit": "📭 **Аудит-лог пуст**\n\nЕщё не было никаких действий.",
}


def empty_state(resource_type: str) -> str:
    """Return empty state message for a resource type."""
    return EMPTY_STATES.get(resource_type, f"📭 Нет данных ({resource_type}).")


# ── Error ────────────────────────────────────────────────────────────────────

def error_text(
    message: str,
    code: str | None = None,
    retry_callback: str | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build error message with optional retry button.

    Returns (text, keyboard).
    """
    lines = ["❌ **Ошибка**"]
    if code:
        lines.append(f"`{code}`")
    lines.append("")
    lines.append(message)
    if code:
        lines.append("")
        lines.append(f"Код: `{code}`")

    kb = None
    if retry_callback:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Повторить", callback_data=retry_callback)],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        )

    return "\n".join(lines), kb


# ── Partial ──────────────────────────────────────────────────────────────────

def partial_state(loaded: int, total: int, loaded_items: list[str]) -> str:
    """Build partial data message."""
    lines = [
        f"⚠️ **Загружено частично** ({loaded}/{total})",
        "",
    ]
    for item in loaded_items:
        lines.append(f"• {item}")
    lines.extend([
        "",
        "_Остальные временно недоступны. Попробуйте обновить._",
    ])
    return "\n".join(lines)


# ── Stale ────────────────────────────────────────────────────────────────────

def stale_confirm_text(resource_name: str, action_label: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build stale confirmation message with refresh option."""
    text = (
        f"⏰ **Время подтверждения истекло**\n\n"
        f"Действие **{action_label}** для **{resource_name}** "
        f"не было выполнено, так как код подтверждения устарел "
        f"(TTL 45 сек).\n\n"
        f"Вернитесь в карточку приложения и повторите попытку."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 К карточке",
                    callback_data=f"back:app:{resource_name}",
                ),
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="menu:main",
                ),
            ],
        ]
    )
    return text, kb


# ── Navigation helpers ───────────────────────────────────────────────────────

def nav_back_main(back_callback: str = "back:app_list") -> InlineKeyboardMarkup:
    """Standard back + main menu keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
            ],
        ]
    )


def nav_main_only() -> InlineKeyboardMarkup:
    """Main menu only keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def nav_retry_back(retry_callback: str, back_callback: str = "back:app_list") -> InlineKeyboardMarkup:
    """Retry + back keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data=retry_callback)],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
            ],
        ]
    )
