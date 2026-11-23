"""base.py -- the Auth contract: the interface every login mode implements."""
from __future__ import annotations

from abc import ABC, abstractmethod

DEFAULT_TIMEOUT_S = 10


class Auth(ABC):
    """The gatekeeper. Any login mode implements authorized_get()."""
    @abstractmethod
    def authorized_get(self, url):
        ...
