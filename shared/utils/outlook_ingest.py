"""Drives Outlook on the web (the AM's signed-in profile, a VISIBLE Chrome window) to do what the AM does for the story HU-02: send an email to himself and move it to the folder "Quotation".
Spanish or English interface. Profile: .mailbox_profile_AM (tools/mailbox_login.py AM). Every email it sends is a REAL email of the AM's account to the AM himself.

  with OutlookSession() as o:
      o.send_to_self(subject, body)          # new email to the AM's own address
      o.move_to_quotation(subject)           # Inbox -> folder "Quotation" (the AM moves it by hand in real life)
"""
import os
import re
import time
from urllib.parse import quote

from shared.utils import mailbox


class OutlookSession:
    def __init__(self, address=None, folder="Quotation"):
        self.address = address or os.environ.get("QUOTATION_AM_EMAIL")
        self.folder = folder
        self._pw = None
        self._ctx = None
        self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._ctx = mailbox._open(self._pw, "AM", False)
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self._warm_up()
        return self

    def _warm_up(self):
        """Opens the inbox first: with a cold session a direct compose link bounces to login.microsoftonline.com (Outlook now lives on outlook.cloud.microsoft); the inbox renews the session."""
        self.page.goto("https://outlook.office.com/mail/inbox", wait_until="domcontentloaded")
        self.page.wait_for_timeout(10000)

    def __exit__(self, *exc):
        try:
            self._ctx.close()
        finally:
            self._pw.stop()

    def _shot(self, name):
        path = os.path.join(os.environ.get("OUTLOOK_SHOTS", "."), f"{name}.png")
        self.page.screenshot(path=path)
        return path

    def send_to_self(self, subject, body, wait_ms=9000, attach=None, plain=False):
        """Opens the compose form with the fields filled (deep link) and sends it with Ctrl+Enter."""
        url = f"https://outlook.office.com/mail/deeplink/compose?to={quote(self.address)}&subject={quote(subject)}&body={quote(body)}"
        if len(url) > 2000:            # a very long link is rejected by the Microsoft sign-in redirect (AADSTS90015, query string too long): renew the session with a short link first
            self.page.goto(f"https://outlook.office.com/mail/deeplink/compose?to={quote(self.address)}&subject=warm", wait_until="domcontentloaded")
            self.page.wait_for_timeout(wait_ms + 4000)
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(wait_ms)
        if "login.microsoftonline.com" in self.page.url:                 # one retry after renewing the session through the inbox
            self._warm_up()
            self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(wait_ms)
        if "login.microsoftonline.com" in self.page.url:
            raise RuntimeError("the AM session of Outlook is gone: python tools/mailbox_login.py AM")
        if plain:                      # Options > Switch to plain text: the email is written without HTML
            self.page.get_by_role("button", name=re.compile(r"^(Enviar|Send)$")).first.wait_for(timeout=90000)
            self.page.get_by_role("tab", name=re.compile(r"^(Opciones|Options)$")).first.click()
            self.page.wait_for_timeout(1500)
            self.page.get_by_role("button", name=re.compile(r"Cambiar a texto sin formato|Switch to plain text")).first.click()
            self.page.get_by_role("button", name=re.compile(r"^(Aceptar|OK)$")).first.click(timeout=15000)      # 'Switching to plain text removes the formatting. Continue?'
            self.page.wait_for_timeout(2500)
            self._shot("outlook_plain_text")
        if attach:
            self.page.get_by_role("button", name=re.compile(r"^(Adjuntar|Attach)")).first.wait_for(timeout=90000)
            self.page.get_by_role("button", name=re.compile(r"^(Adjuntar|Attach)")).first.click()
            self.page.wait_for_timeout(1500)
            with self.page.expect_file_chooser(timeout=15000) as fc:
                self.page.get_by_role("menuitem", name=re.compile(r"Examinar este equipo|Browse this computer")).first.click()
            fc.value.set_files(attach)
            self.page.wait_for_timeout(8000)
            self._shot("outlook_attached")
        send = self.page.get_by_role("button", name=re.compile(r"^(Enviar|Send)$")).first
        send.wait_for(timeout=90000)          # after the silent sign-in of Microsoft the composer can take longer than the fixed wait
        send.click(timeout=60000)                                         # Ctrl+Enter is not taken when the focus is not in the body
        self.page.wait_for_timeout(5000)

    def _open_inbox_search(self, text):
        self.page.goto("https://outlook.office.com/mail/inbox", wait_until="domcontentloaded")
        self.page.wait_for_timeout(8000)
        self.page.locator("input[placeholder='Buscar'], input[placeholder='Search']").first.click()
        self.page.keyboard.type(text)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(5000)

    def move_to_quotation(self, subject, timeout=120):
        """Waits for the email to arrive, selects it and moves it with the Move-to menu (key V) to the folder."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._open_inbox_search(subject)
            items = self.page.locator("[role='option'][data-convid]")
            if items.count():
                items.first.click()
                self.page.wait_for_timeout(2500)
                self.page.keyboard.press("v")                 # Move to
                self.page.wait_for_timeout(1500)
                self.page.keyboard.type(self.folder)
                self.page.wait_for_timeout(1500)
                self._shot("outlook_move_menu")
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(3000)
                return True
            self.page.wait_for_timeout(8000)
        return False

    def move_many(self, prefix, count, timeout=180):
        """Waits until `count` emails whose subject starts with `prefix` are in the Inbox, selects exactly those (click + Ctrl+click on the rows tagged with the Inbox, not the copies of
        Sent Items) and moves them together to the folder, as a drag of a selection does. The window is made tall because Outlook only draws the rows that fit.
        Returns the UTC time (naive) of the move, or None."""
        import datetime as dt
        self.page.set_viewport_size({"width": 1400, "height": 2600})
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._open_inbox_search(prefix)
            rows = self.page.locator("[role='option'][data-convid]").filter(has_text=re.compile(r"Bandeja de entr|Inbox"))
            if rows.count() >= count:
                rows.first.click()
                for i in range(1, rows.count()):
                    rows.nth(i).click(modifiers=["Control"])
                self.page.wait_for_timeout(1500)
                self.page.keyboard.press("v")
                self.page.wait_for_timeout(1500)
                self.page.keyboard.type(self.folder)
                self.page.wait_for_timeout(1500)
                self._shot("outlook_move_many_menu")
                moved = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(3000)
                # VERIFY: no email of the batch may stay in the Inbox (an email that arrives late or is missed by the selection is moved again). The time returned is the one of the first move.
                for _ in range(4):
                    self._open_inbox_search(prefix)
                    left = self.page.locator("[role='option'][data-convid]").filter(has_text=re.compile(r"Bandeja de entr|Inbox"))
                    if not left.count():
                        break
                    left.first.click()
                    for i in range(1, left.count()):
                        left.nth(i).click(modifiers=["Control"])
                    self.page.keyboard.press("v")
                    self.page.wait_for_timeout(1500)
                    self.page.keyboard.type(self.folder)
                    self.page.wait_for_timeout(1500)
                    self.page.keyboard.press("Enter")
                    self.page.wait_for_timeout(3000)
                else:
                    raise RuntimeError(f"emails of the batch {prefix} are still in the Inbox after moving them")
                return moved
            self.page.wait_for_timeout(8000)
        self._shot("outlook_move_many_notfound")
        return None

    def move_to(self, subject, folder, key="v", timeout=90):
        """Moves ONE email (found by subject, in any folder) to another folder with the Move-to menu; folder is typed in the menu ('Bandeja de entrada' / 'Quotation')."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._open_inbox_search(subject)
            items = self.page.locator("[role='option'][data-convid]")
            if items.count():
                items.first.click()
                self.page.wait_for_timeout(2000)
                self.page.keyboard.press(key)
                self.page.wait_for_timeout(1500)
                self.page.keyboard.type(folder)
                self.page.wait_for_timeout(1500)
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(3000)
                return True
            self.page.wait_for_timeout(5000)
        return False

    def delete(self, subject, timeout=90):
        """Deletes ONE email (found by subject) with the Delete key (it goes to Deleted Items)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._open_inbox_search(subject)
            items = self.page.locator("[role='option'][data-convid]")
            if items.count():
                items.first.click()
                self.page.wait_for_timeout(2000)
                self.page.keyboard.press("Delete")
                self.page.wait_for_timeout(3000)
                return True
            self.page.wait_for_timeout(5000)
        return False

    def mark_unread(self, subject, timeout=90):
        """Selects ONE email (found by subject) and marks it as unread with Ctrl+U (Outlook on the web)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._open_inbox_search(subject)
            items = self.page.locator("[role='option'][data-convid]")
            if items.count():
                items.first.click()
                self.page.wait_for_timeout(2000)
                self.page.keyboard.press("Control+u")
                self.page.wait_for_timeout(2000)
                self._shot("outlook_mark_unread")
                return True
            self.page.wait_for_timeout(5000)
        return False
