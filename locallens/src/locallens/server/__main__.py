"""python -m locallens.server  (run the server)   |   python -m locallens.server create-user NAME [--admin]"""
from __future__ import annotations

import argparse
import getpass
import sys

from .config import Settings


def main() -> None:
    ap = argparse.ArgumentParser(prog="locallens.server")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the server (default)")
    cu = sub.add_parser("create-user", help="create a user from the command line")
    cu.add_argument("username")
    cu.add_argument("--admin", action="store_true")
    rp = sub.add_parser("reset-password", help="set a new password for a user")
    rp.add_argument("username")
    args = ap.parse_args()
    s = Settings()

    if args.cmd in ("create-user", "reset-password"):
        from .db import Database
        from .security import check_password_strength, hash_password

        db = Database(s.db_path)
        pw = getpass.getpass("Password: ")
        try:
            check_password_strength(pw, args.username)
        except ValueError as e:
            sys.exit(str(e))
        if args.cmd == "create-user":
            db.run("INSERT INTO users (username, pw_hash, role) VALUES (?, ?, ?)",
                   (args.username, hash_password(pw), "admin" if args.admin else "user"))
            print(f"Created {'admin' if args.admin else 'user'} {args.username}.")
        else:
            n = db.run("UPDATE users SET pw_hash = ?, must_change_password = 0 WHERE username = ?",
                       (hash_password(pw), args.username))
            db.run("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username = ?)", (args.username,))
            print("Password updated." if n else "No such user.")
        return

    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":
    main()
