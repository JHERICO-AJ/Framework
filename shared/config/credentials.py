"""Single place to read credentials. Priority: environment variables / .env, and
as a compatibility fallback, the old omniops_login.txt. Never hardcode credentials."""
from __future__ import annotations

import os


def _load_dotenv(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_credentials():
    """Returns {'email': ..., 'password': ...} or raises if there are none."""
    _load_dotenv()
    email = os.environ.get("OMNIOPS_EMAIL")
    password = os.environ.get("OMNIOPS_PASSWORD")
    if email and password:
        return {"email": email, "password": password}
    # compat: omniops_login.txt (email on one line, password on another)
    if os.path.exists("omniops_login.txt"):
        lines = [l.strip() for l in open("omniops_login.txt", encoding="utf-8") if l.strip()]
        if len(lines) >= 2:
            return {"email": lines[0], "password": lines[1]}
    raise RuntimeError("No credentials found. Set OMNIOPS_EMAIL and OMNIOPS_PASSWORD "
                       "in a .env file (see .env.example).")
