"""
auth.py — login a OmniOps, en DOS formas. El resto del framework no cambia:
solo le pide datos al "portero" con auth.authorized_get(url).

  TokenAuth  : email/contraseña -> token JWT. Se renueva SOLO. Ideal para
               automatizar y correr en tiempo real. Lee 'omniops_login.txt'.
  CookieAuth : reutiliza la cookie de sesión del navegador (para login
               Microsoft de compañía). Lee 'omniops_cookie.txt'.

make_auth() elige sola según qué archivo tengas creado en la carpeta.
Ninguno de los dos escribe nada en OmniOps: solo leen.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod


def _parse_dt(s):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        s = re.sub(r"(\.\d{6})\d+", r"\1", s)
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


class Auth(ABC):
    """El portero. Cualquier modo de login implementa authorized_get()."""
    @abstractmethod
    def authorized_get(self, url):
        ...


# ---------------------------------------------------------------------------
# MODO 1 — email/contraseña (token que se renueva solo)
# ---------------------------------------------------------------------------
class TokenAuth(Auth):
    def __init__(self, base_url, creds_path="omniops_login.txt"):
        self.base_url = base_url.rstrip("/")
        self.creds_path = creds_path
        self._token = None
        self._expires_at = None

    def _load_creds(self):
        if not os.path.exists(self.creds_path):
            raise FileNotFoundError(
                f"Falta '{self.creds_path}' con:\n    email=...\n    password=...")
        creds = {}
        for line in open(self.creds_path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip().lower()] = v.strip()
        if "email" not in creds or "password" not in creds:
            raise ValueError("El archivo debe tener 'email=...' y 'password=...'")
        return creds

    def login(self):
        creds = self._load_creds()
        url = f"{self.base_url}/api/ExternalUserAuth/login"
        body = json.dumps({"email": creds["email"],
                           "password": creds["password"]}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        self._token = data["token"]
        self._expires_at = _parse_dt(data.get("expiresAt"))
        return self._token

    def _still_valid(self):
        if not self._token:
            return False
        if self._expires_at is None:
            return True
        now = datetime.datetime.now(datetime.timezone.utc)
        return now < self._expires_at - datetime.timedelta(seconds=15)

    def token(self):
        if not self._still_valid():
            self.login()
        return self._token

    def authorized_get(self, url):
        for attempt in (1, 2):
            tok = self.token()
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {tok}"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 1:
                    self._token = None   # re-loguea y reintenta una vez
                    continue
                raise


# ---------------------------------------------------------------------------
# MODO 2 — cookie del navegador (login Microsoft)
# ---------------------------------------------------------------------------
class CookieAuth(Auth):
    def __init__(self, cookie_path="omniops_cookie.txt"):
        self.cookie_path = cookie_path

    def _load_cookie(self):
        if not os.path.exists(self.cookie_path):
            raise FileNotFoundError(
                f"Falta '{self.cookie_path}'. Pegá ahí la cookie de sesión "
                "copiada del navegador (ver instrucciones).")
        cookie = open(self.cookie_path, encoding="utf-8").read().strip()
        if not cookie:
            raise ValueError(f"'{self.cookie_path}' está vacío.")
        return cookie

    def authorized_get(self, url):
        req = urllib.request.Request(
            url, headers={"Cookie": self._load_cookie()})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(
                    "La cookie venció o no es válida. Volvé a copiarla del "
                    "navegador a 'omniops_cookie.txt'.") from e
            raise


# ---------------------------------------------------------------------------
# Elige el modo solo, según qué archivo exista
# ---------------------------------------------------------------------------
def make_auth(base_url):
    if os.path.exists("omniops_login.txt"):
        return TokenAuth(base_url)          # preferido: se renueva solo
    if os.path.exists("omniops_cookie.txt"):
        return CookieAuth()
    raise FileNotFoundError(
        "No hay credenciales. Creá UNO de estos archivos en la carpeta:\n"
        "  - 'omniops_login.txt'  (email/contraseña)  -> modo token\n"
        "  - 'omniops_cookie.txt' (cookie del navegador) -> modo Microsoft")
