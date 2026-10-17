"""Passwords, session tokens and login throttling. Standard library only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
MIN_PASSWORD = 8


class WeakPassword(ValueError):
    pass


def check_password_strength(pw: str, username: str = "") -> None:
    if len(pw) < MIN_PASSWORD:
        raise WeakPassword(f"Use at least {MIN_PASSWORD} characters.")
    if username and pw.lower() == username.lower():
        raise WeakPassword("The password cannot be the same as the username.")
    if pw.lower() in {"password", "12345678", "qwertyui", "password1", "11111111"}:
        raise WeakPassword("That password is too common.")


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(SCRYPT_N, SCRYPT_R, SCRYPT_P,
                                          base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


# a fixed hash so unknown usernames cost the same time as wrong passwords
DUMMY_HASH = hash_password(secrets.token_urlsafe(8))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginThrottle:
    """Lock a (username, ip) pair for a while after too many failures."""

    def __init__(self, max_failures: int, lock_minutes: float):
        self.max_failures, self.lock_s = max_failures, lock_minutes * 60
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        now = time.monotonic()
        recent = [t for t in self._fails.get(key, []) if now - t < self.lock_s]
        self._fails[key] = recent
        return recent

    def blocked(self, key: str) -> float:
        """Seconds left on the lock, or 0."""
        with self._lock:
            recent = self._recent(key)
            if len(recent) >= self.max_failures:
                return self.lock_s - (time.monotonic() - recent[0])
            return 0.0

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
