"""Única lectura de credenciales. Prioridad: variables de entorno / .env, y como
compatibilidad, el viejo omniops_login.txt. Nunca hardcodear credenciales."""
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
    """Devuelve {'email': ..., 'password': ...} o lanza si no hay."""
    _load_dotenv()
    email = os.environ.get("OMNIOPS_EMAIL")
    password = os.environ.get("OMNIOPS_PASSWORD")
    if email and password:
        return {"email": email, "password": password}
    # compat: omniops_login.txt (email en una línea, password en otra)
    if os.path.exists("omniops_login.txt"):
        lineas = [l.strip() for l in open("omniops_login.txt", encoding="utf-8") if l.strip()]
        if len(lineas) >= 2:
            return {"email": lineas[0], "password": lineas[1]}
    raise RuntimeError("No hay credenciales. Definí OMNIOPS_EMAIL y OMNIOPS_PASSWORD "
                       "en un archivo .env (ver .env.example).")
