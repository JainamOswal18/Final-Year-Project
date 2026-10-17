"""Request authentication: cookie session, CSRF header, role checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from .runtime import Runtime
from .security import new_token, token_hash

COOKIE = "ll_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "LocalLens"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _later(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def runtime(request: Request) -> Runtime:
    return request.app.state.rt


def create_session(rt: Runtime, user_id: int) -> str:
    token = new_token()
    with rt.db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
        c.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                  (token_hash(token), user_id, _later(rt.settings.session_hours)))
    return token


def end_session(rt: Runtime, token: str | None) -> None:
    if token:
        rt.db.run("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))


def _user_from_cookie(request: Request, rt: Runtime):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = rt.db.one(
        "SELECT u.*, s.expires_at AS s_exp FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1", (token_hash(token), _now()))
    if row and row["s_exp"] < _later(rt.settings.session_hours / 2):      # sliding expiry
        rt.db.run("UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                  (_later(rt.settings.session_hours), token_hash(token)))
    return row


def current_user_any(request: Request, rt: Runtime = Depends(runtime)):
    """Signed in (even if a password change is still pending)."""
    user = _user_from_cookie(request, rt)
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


def current_user(user=Depends(current_user_any)):
    if user["must_change_password"]:
        raise HTTPException(403, "password_change_required")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrators only.")
    return user


def audit(rt: Runtime, user_id: int | None, action: str, detail: str = "") -> None:
    rt.db.run("INSERT INTO audit (user_id, action, detail) VALUES (?, ?, ?)", (user_id, action, detail[:500]))
