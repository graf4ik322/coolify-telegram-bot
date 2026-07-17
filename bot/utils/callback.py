"""Callback data encoding/decoding utilities.

Telegram callback_data has a 64-byte limit. UUIDs (36 chars) are safe to use
directly as they don't contain the ``:`` delimiter. For arbitrary strings like
app names, we use a simple reference approach instead of embedding them.

This module is kept for compatibility; most callback data now uses plain UUIDs.
"""

from __future__ import annotations

import base64


def enc(data: str) -> str:
    """Encode a string for safe embedding in callback data.

    Only needed when the value may contain ``:`` or other Telegram-special chars.
    UUIDs are safe without encoding.
    """
    return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")


def dec(encoded: str) -> str:
    """Decode a callback-encoded string."""
    # Add padding if stripped
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding
    return base64.urlsafe_b64decode(encoded).decode()
