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


# Quotation test accounts, one per role (app login only -- native email/password form). Each role reads
# QUOTATION_<ROLE>_EMAIL / QUOTATION_<ROLE>_PASSWORD from .env. The DEFAULT_* ones are the approvers the system
# assigns on its own from the amount rules. NOROLE is a user with no Quotation role at all. AM2 is a second AM,
# used to check that one AM cannot see or change the quotations of another.
QUOTATION_ROLES = ("AM", "AM2", "FPM", "BU", "CEO", "DEFAULT_FPM", "DEFAULT_BU", "DEFAULT_CEO", "NOROLE")


def load_role_credentials(role):
    """Returns {'email': ..., 'password': ...} for a Quotation test role, or None if not set in .env."""
    if role not in QUOTATION_ROLES:
        raise ValueError(f"role must be one of {QUOTATION_ROLES}, got {role!r}")
    _load_dotenv()
    email = os.environ.get(f"QUOTATION_{role}_EMAIL")
    password = os.environ.get(f"QUOTATION_{role}_PASSWORD")
    return {"email": email, "password": password} if email and password else None
