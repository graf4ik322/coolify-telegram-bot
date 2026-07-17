"""Security utilities — one-time confirmation tokens.

Uses a dedicated ``CONFIRM_SECRET_KEY`` (separate from the Telegram bot token)
for HMAC signing. Falls back to ``bot_token`` only if the dedicated key is
not configured, emitting a warning.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

from bot.config import settings

log = logging.getLogger(__name__)

# Use dedicated secret if available, fall back to bot_token
_hmac_key: bytes = (settings.confirm_secret_key or settings.bot_token).encode()
if not settings.confirm_secret_key:
    log.warning(
        "CONFIRM_SECRET_KEY not set — using BOT_TOKEN as HMAC key. "
        "Set CONFIRM_SECRET_KEY for proper separation of secrets."
    )


@dataclass
class ConfirmToken:
    """A single-use confirmation token with TTL."""

    value: str
    action: str  # restart | stop | start | redeploy
    resource_uuid: str
    resource_name: str
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


def make_confirm_token(action: str, resource_uuid: str, resource_name: str) -> ConfirmToken:
    """Create a time-limited confirmation token.

    The token is HMAC-SHA256 signed so callbacks can be verified server-side
    without storing state (stateless confirmation).
    """
    expires_at = time.time() + settings.confirm_ttl_seconds
    raw = f"{action}:{resource_uuid}:{resource_name}:{int(expires_at)}"
    sig = hmac.new(
        _hmac_key,
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    token_str = f"{sig}:{int(expires_at)}:{resource_uuid}:{action}"
    return ConfirmToken(
        value=token_str,
        action=action,
        resource_uuid=resource_uuid,
        resource_name=resource_name,
        expires_at=expires_at,
    )


def verify_confirm_token(token_str: str) -> ConfirmToken | None:
    """Verify and decode a confirmation token.

    Returns ``None`` if the token is invalid, tampered, or expired.
    """
    parts = token_str.split(":", 3)
    if len(parts) != 4:
        return None
    sig_given, exp_str, resource_uuid, action = parts
    try:
        expires_at = float(exp_str)
    except ValueError:
        return None

    if time.time() > expires_at:
        return None

    # Recompute signature
    raw = f"{action}:{resource_uuid}:?:{int(expires_at)}"
    sig_expected = hmac.new(
        _hmac_key,
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]

    if not hmac.compare_digest(sig_given, sig_expected):
        return None

    return ConfirmToken(
        value=token_str,
        action=action,
        resource_uuid=resource_uuid,
        resource_name="?",
        expires_at=expires_at,
    )


__all__ = ["ConfirmToken", "make_confirm_token", "verify_confirm_token"]
