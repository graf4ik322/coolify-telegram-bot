"""Simple thread-safe TTL cache with bounded size.

Falls back to dict-based storage with periodic cleanup.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """In-memory cache with per-item TTL and bounded size.

    Automatically evicts expired entries on access and insertion.
    Keeps the cache bounded to *max_size* entries.
    """

    def __init__(self, default_ttl: float = 300.0, max_size: int = 1000) -> None:
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._store: OrderedDict[K, tuple[float, float, V]] = OrderedDict()
        #  (expires_at, inserted_at, value)

    def _evict(self) -> None:
        now = time.time()
        # Remove expired entries
        expired = [k for k, (exp, _, _) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]
        # Trim to max_size
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def get(self, key: K, default: V | None = None) -> V | None:
        self._evict()
        item = self._store.get(key)
        if item is None:
            return default
        exp, _, value = item
        if exp <= time.time():
            del self._store[key]
            return default
        return value

    def __setitem__(self, key: K, value: V) -> None:
        self._evict()
        exp = time.time() + self._default_ttl
        self._store[key] = (exp, time.time(), value)

    def __getitem__(self, key: K) -> V:
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        self._evict()
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
