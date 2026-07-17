"""Formatting helpers for Telegram messages."""

from __future__ import annotations

from bot.config import settings
from bot.services.models import Application, ApplicationDeploymentQueue, Server


def status_emoji(status: str | None) -> str:
    """Map Coolify status to Telegram emoji indicator.

    Rules:
      - Contains "running" → 🟢 (health/unknown/unhealthy — всё равно зелёный)
      - Contains "exited"/"stopped" → 🔴
      - "deploying"/"building"/"queued"/"processing"/"starting" → 🟡
      - "degraded"/"unhealthy"/"error" (без "running") → ⚠️
    """
    if not status:
        return "⚪"
    s = status.lower().strip()

    if "running" in s:
        return "🟢"
    if "exited" in s or "stopped" in s:
        return "🔴"
    if s in ("deploying", "building", "queued", "processing", "starting"):
        return "🟡"
    if s in ("degraded", "unhealthy", "error"):
        return "⚠️"
    return "⚪"


def fmt_relative_time(iso_str: str | None) -> str:
    """Return a human-friendly relative time string.

    Handles ISO 8601 strings like ``2026-07-17T10:30:00Z``.
    Falls back to raw string on parse failure.
    """
    if not iso_str:
        return "никогда"
    try:
        from datetime import datetime, timezone

        # Strip trailing Z and parse
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - dt
        total_seconds = int(diff.total_seconds())
        if total_seconds < 0:
            return "только что"
        if total_seconds < 60:
            return f"{total_seconds} сек назад"
        if total_seconds < 3600:
            return f"{total_seconds // 60} мин назад"
        if total_seconds < 86400:
            return f"{total_seconds // 3600} ч назад"
        days = total_seconds // 86400
        return f"{days} дн назад"
    except (ValueError, TypeError):
        return iso_str or "неизвестно"


def format_app_short(app: Application) -> str:
    """One-line app summary for list views."""
    emoji = status_emoji(app.status)
    name = app.name or app.uuid[:8]
    fqdn = f" — {app.fqdn}" if app.fqdn else ""
    return f"{emoji} **{name}**{fqdn}"


def format_app_card(app: Application, deploy: ApplicationDeploymentQueue | None = None) -> str:
    """Full application card for ``/status`` or inline detail."""
    lines: list[str] = [
        f"{status_emoji(app.status)} **{app.name}**",
        f"`{app.uuid}`",
        "",
    ]
    if app.fqdn:
        lines.append(f"🌐 **Домен:** {app.fqdn}")
    if app.git_repository:
        repo = app.git_repository.rstrip(".git").split("/")[-1] if "/" in app.git_repository else app.git_repository
        lines.append(f"📦 **Репозиторий:** `{repo}` [{app.git_branch or 'default'}]")
    elif app.docker_registry_image_name:
        tag = app.docker_registry_image_tag or "latest"
        lines.append(f"📦 **Образ:** `{app.docker_registry_image_name}:{tag}`")
    if app.build_pack:
        lines.append(f"🔧 **Build pack:** `{app.build_pack}`")
    if app.destination_docker:
        lines.append(f"🐳 **Docker:** `{app.destination_docker}`")

    lines.append(f"\n**Статус:** {status_emoji(app.status)} {app.status or 'неизвестен'}")

    if app.updated_at:
        lines.append(f"🕐 **Обновлено:** {fmt_relative_time(app.updated_at)}")

    # Deployment info
    if deploy:
        ds = status_emoji(deploy.status)
        lines.extend([
            "",
            f"**Последний деплой:** {ds} {deploy.status or 'N/A'}",
        ])
        if deploy.commit_sha:
            sha = deploy.commit_sha[:7] if len(deploy.commit_sha) > 7 else deploy.commit_sha
            lines.append(f"  📝 `{sha}` {deploy.commit_message or ''}")
        if deploy.started_at:
            lines.append(f"  🕐 {fmt_relative_time(deploy.started_at)}")

    return "\n".join(lines)


def format_server_short(srv: Server) -> str:
    """One-line server summary."""
    reachable = "🟢" if srv.is_reachable else "🔴"
    ip = srv.ip or srv.host or "?"
    return f"{reachable} **{srv.name}** — `{ip}`"


def format_logs(logs: str, max_len: int = 4000) -> tuple[str, str | None]:
    """Split logs into inline message + optional file content.

    Returns ``(message_text, file_content)`` where
    ``file_content`` is ``None`` when logs fit in the message.
    """
    import re

    # Remove ANSI escape sequences
    clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", logs)

    if len(clean) <= max_len:
        return f"```\n{clean}\n```", None

    # Truncate to fit with a note
    truncated = clean[-max_len:]
    return (
        f"```\n... (показаны последние {max_len} символов из {len(clean)})\n{truncated}\n```",
        clean,
    )


def fmt_deployment_status(d: ApplicationDeploymentQueue) -> str:
    """Format a single deployment queue entry."""
    emoji = status_emoji(d.status)
    sha = (d.commit_sha or "?")[:7]
    msg = d.commit_message or ""
    started = fmt_relative_time(d.started_at)
    return f"{emoji} `{sha}` {msg} — {started} [{d.status}]"


def truncate_text(text: str, max_len: int = 256) -> str:
    """Truncate text to max_len, appending ``…`` if cut."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


__all__ = [
    "fmt_relative_time",
    "fmt_deployment_status",
    "format_app_card",
    "format_app_short",
    "format_logs",
    "format_server_short",
    "status_emoji",
    "truncate_text",
]
