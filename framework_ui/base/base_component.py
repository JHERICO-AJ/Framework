"""BaseComponent — common to every reusable component (a piece within a page)."""
from __future__ import annotations


class BaseComponent:
    def __init__(self, page, root=None):
        self.page = page
        # root: the component's root locator (to scope the search to it)
        self.root = page.locator(root) if isinstance(root, str) else (root or page)
