"""BaseComponent — común a todo componente reutilizable (una pieza dentro de una page)."""
from __future__ import annotations


class BaseComponent:
    def __init__(self, page, root=None):
        self.page = page
        # root: locator raíz del componente (para acotar la búsqueda a su scope)
        self.root = page.locator(root) if isinstance(root, str) else (root or page)
