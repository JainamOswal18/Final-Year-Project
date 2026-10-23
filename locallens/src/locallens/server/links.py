"""Short-lived, single-use download links for the Windows helper.

The helper that opens a chart in Power BI Desktop is not the browser, so it has no sign-in cookie. When a signed-in
person clicks "Open in Power BI", the server makes one of these links for that one export. It works once, for two
minutes, and only for the person and answer it was made for. Held in memory: a server restart cancels pending links."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

TTL_SECONDS = 120
MAX_PENDING = 500


@dataclass(frozen=True)
class Grant:
    user_id: int
    message_id: str
    kind: str


class LinkStore:
    def __init__(self, ttl: float = TTL_SECONDS, clock=time.monotonic):
        self._ttl, self._clock = ttl, clock
        self._items: dict[str, tuple[float, Grant]] = {}
        self._lock = threading.Lock()

    def _prune(self) -> None:
        now = self._clock()
        for t in [t for t, (exp, _) in self._items.items() if exp <= now]:
            del self._items[t]
        while len(self._items) > MAX_PENDING:                      # drop the oldest
            del self._items[min(self._items, key=lambda t: self._items[t][0])]

    def issue(self, user_id: int, message_id: str, kind: str) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._prune()
            self._items[token] = (self._clock() + self._ttl, Grant(user_id, message_id, kind))
        return token

    def redeem(self, token: str) -> Grant | None:
        """The grant behind a token, once. A used, unknown or expired token gives None."""
        with self._lock:
            self._prune()
            item = self._items.pop(token, None)
        return item[1] if item else None
