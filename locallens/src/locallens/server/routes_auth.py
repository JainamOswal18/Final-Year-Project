"""Sign-in, first-run setup, password change and user administration."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .auth import COOKIE, admin_user, audit, create_session, current_user_any, end_session, runtime
from .runtime import Runtime
from .security import DUMMY_HASH, WeakPassword, check_password_strength, hash_password, token_hash, verify_password

router = APIRouter(prefix="/api")
USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,40}$")


class Credentials(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class NewUser(BaseModel):
    username: str
    role: str = "user"
    password: str | None = None


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    new_password: str | None = None


def user_dict(u) -> dict:
    return {"id": u["id"], "username": u["username"], "role": u["role"],
            "must_change_password": bool(u["must_change_password"]),
            "active": bool(u["active"]), "last_login": u["last_login"], "created_at": u["created_at"]}


def _set_cookie(request: Request, response: Response, rt: Runtime, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=int(rt.settings.session_hours * 3600), httponly=True,
                        samesite="lax", secure=rt.settings.secure_cookies, path="/")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/auth/status")
def status(request: Request, rt: Runtime = Depends(runtime)):
    n = rt.db.one("SELECT count(*) AS n FROM users")["n"]
    return {"setup_required": n == 0}


@router.post("/auth/setup")
def setup(body: Credentials, request: Request, response: Response, rt: Runtime = Depends(runtime)):
    """First run only: create the administrator."""
    if not USERNAME.match(body.username):
        raise HTTPException(422, "Username: 3-40 letters, digits, dot, dash or underscore.")
    try:
        check_password_strength(body.password, body.username)
    except WeakPassword as e:
        raise HTTPException(422, str(e)) from e
    with rt.db.tx() as c:                                  # the check and the insert are one step
        if c.execute("SELECT count(*) FROM users").fetchone()[0]:
            raise HTTPException(409, "Setup is already done.")
        uid = c.execute("INSERT INTO users (username, pw_hash, role) VALUES (?, ?, 'admin')",
                        (body.username, hash_password(body.password))).lastrowid
    rt.db.run("UPDATE users SET last_login = datetime('now') WHERE id = ?", (uid,))
    audit(rt, uid, "setup", body.username)
    _set_cookie(request, response, rt, create_session(rt, uid))
    return user_dict(rt.db.one("SELECT * FROM users WHERE id = ?", (uid,)))


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, rt: Runtime = Depends(runtime)):
    key = f"{body.username.lower()}|{_client_ip(request)}"
    wait = rt.throttle.blocked(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts. Try again in {int(wait // 60) + 1} minute(s).")
    row = rt.db.one("SELECT * FROM users WHERE username = ?", (body.username,))
    ok = verify_password(body.password, row["pw_hash"] if row else DUMMY_HASH)   # same cost either way
    if not (row and ok and row["active"]):
        rt.throttle.fail(key)
        audit(rt, row["id"] if row else None, "login_failed", body.username)
        raise HTTPException(401, "Wrong username or password.")
    rt.throttle.reset(key)
    rt.db.run("UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],))
    audit(rt, row["id"], "login")
    _set_cookie(request, response, rt, create_session(rt, row["id"]))
    return user_dict(row)


@router.post("/auth/logout")
def logout(request: Request, response: Response, rt: Runtime = Depends(runtime)):
    end_session(rt, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(current_user_any)):
    return user_dict(user)


@router.post("/auth/password")
def change_password(body: PasswordChange, request: Request, user=Depends(current_user_any), rt: Runtime = Depends(runtime)):
    if not verify_password(body.current_password, user["pw_hash"]):
        raise HTTPException(403, "The current password is wrong.")
    try:
        check_password_strength(body.new_password, user["username"])
    except WeakPassword as e:
        raise HTTPException(422, str(e)) from e
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a different password.")
    keep = token_hash(request.cookies.get(COOKIE, ""))
    with rt.db.tx() as c:
        c.execute("UPDATE users SET pw_hash = ?, must_change_password = 0 WHERE id = ?",
                  (hash_password(body.new_password), user["id"]))
        c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user["id"], keep))
    audit(rt, user["id"], "password_changed")
    return {"ok": True}


# ---- administration ---------------------------------------------------------------------
@router.get("/users")
def list_users(admin=Depends(admin_user), rt: Runtime = Depends(runtime)):
    return [user_dict(u) for u in rt.db.all("SELECT * FROM users ORDER BY username")]


@router.post("/users")
def create_user(body: NewUser, admin=Depends(admin_user), rt: Runtime = Depends(runtime)):
    if not USERNAME.match(body.username):
        raise HTTPException(422, "Username: 3-40 letters, digits, dot, dash or underscore.")
    if body.role not in ("admin", "user"):
        raise HTTPException(422, "Role must be admin or user.")
    temp = body.password or secrets.token_urlsafe(9)
    try:
        check_password_strength(temp, body.username)
    except WeakPassword as e:
        raise HTTPException(422, str(e)) from e
    if rt.db.one("SELECT 1 FROM users WHERE username = ?", (body.username,)):
        raise HTTPException(409, "That username is taken.")
    uid = None
    with rt.db.tx() as c:
        uid = c.execute("INSERT INTO users (username, pw_hash, role, must_change_password) VALUES (?, ?, ?, 1)",
                        (body.username, hash_password(temp), body.role)).lastrowid
    audit(rt, admin["id"], "user_created", body.username)
    return {**user_dict(rt.db.one("SELECT * FROM users WHERE id = ?", (uid,))), "temporary_password": temp}


def _other_active_admins(rt: Runtime, user_id: int) -> int:
    return rt.db.one("SELECT count(*) AS n FROM users WHERE role = 'admin' AND active = 1 AND id != ?", (user_id,))["n"]


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, admin=Depends(admin_user), rt: Runtime = Depends(runtime)):
    target = rt.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if target is None:
        raise HTTPException(404, "No such user.")
    losing_admin = target["role"] == "admin" and (body.role == "user" or body.active is False)
    if losing_admin and not _other_active_admins(rt, user_id):
        raise HTTPException(409, "There must be at least one active administrator.")
    if body.role is not None and body.role not in ("admin", "user"):
        raise HTTPException(422, "Role must be admin or user.")
    temp = None
    with rt.db.tx() as c:
        if body.role is not None:
            c.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
        if body.active is not None:
            c.execute("UPDATE users SET active = ? WHERE id = ?", (int(body.active), user_id))
            if not body.active:
                c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if body.new_password is not None:
            temp = body.new_password or secrets.token_urlsafe(9)
            try:
                check_password_strength(temp, target["username"])
            except WeakPassword as e:
                raise HTTPException(422, str(e)) from e
            c.execute("UPDATE users SET pw_hash = ?, must_change_password = 1 WHERE id = ?", (hash_password(temp), user_id))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    audit(rt, admin["id"], "user_updated", f"{target['username']} {body.model_dump(exclude={'new_password'})}")
    out = user_dict(rt.db.one("SELECT * FROM users WHERE id = ?", (user_id,)))
    return {**out, "temporary_password": temp} if temp else out


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin=Depends(admin_user), rt: Runtime = Depends(runtime)):
    target = rt.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if target is None:
        raise HTTPException(404, "No such user.")
    if target["role"] == "admin" and not _other_active_admins(rt, user_id):
        raise HTTPException(409, "There must be at least one active administrator.")
    import shutil
    for d in rt.db.all("SELECT id FROM datasets WHERE owner_id = ?", (user_id,)):
        rt.invalidate(d["id"])
        shutil.rmtree(rt.dataset_dir(d["id"]), ignore_errors=True)
    rt.db.run("DELETE FROM users WHERE id = ?", (user_id,))
    audit(rt, admin["id"], "user_deleted", target["username"])
    return {"ok": True}
