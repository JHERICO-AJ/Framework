"""shared.auth — login to OmniOps. See shared.auth.factory.make_auth().

Re-exports the public names so old imports (e.g.
`from shared.auth.auth import make_auth`) still resolve via this package if
needed, though new code should import from the specific module
(shared.auth.factory, shared.auth.token_auth, shared.auth.cookie_auth).
"""
from __future__ import annotations

from shared.auth.base import Auth
from shared.auth.cookie_auth import CookieAuth
from shared.auth.factory import make_auth
from shared.auth.token_auth import TokenAuth

__all__ = ["Auth", "TokenAuth", "CookieAuth", "make_auth"]
