"""Configuration for Coolify Telegram Bot."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    bot_token: str

    # Coolify API
    coolify_api_url: str = "https://app.coolify.io"
    coolify_api_token: str

    # Redis (optional — without it rate-limit uses in-memory fallback)
    redis_url: str | None = None

    # Database
    database_url: str = "sqlite+aiosqlite:///app/data/bot.db"

    # Admin user IDs (comma-separated)
    admin_ids: str = ""

    # Behaviour
    log_level: str = "INFO"
    confirm_secret_key: str | None = None
    confirm_ttl_seconds: int = 45
    rate_limit_per_minute: int = 10
    restart_cooldown_seconds: int = 120
    logs_default_lines: int = 50

    @property
    def admin_telegram_ids(self) -> set[int]:
        """Parse admin IDs into a set of integers."""
        if not self.admin_ids:
            return set()
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}


settings = Settings()  # type: ignore[call-arg]
