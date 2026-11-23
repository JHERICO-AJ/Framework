"""Reads the notification emails of the test accounts (AM, FPM, BU, CEO and the QA Default approvers) in a browser profile that a person signed in ONCE.
Same idea as shared/utils/oem_mailbox.py but for any role, and it returns ALL the emails of a quotation (subject, sender, body, links), not a decision link.

  python tools/mailbox_login.py <ROLE>     one time per role: opens Chrome on that role's profile; sign in, open the inbox, close Chrome.
  fetch_emails(role, quote_no)             [{'subject','sender','body'}, ...] oldest first, or None when the profile is missing or the session is gone.

Roles: AM (Outlook on the web) and FPM, BU, CEO, DEFAULT_FPM, DEFAULT_BU, DEFAULT_CEO (Gmail). The profile folders (.mailbox_profile_<ROLE>) hold real sessions: they are ignored by git and must never be shared."""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROVIDER = {"AM": "outlook", "FPM": "gmail", "BU": "gmail", "CEO": "gmail", "DEFAULT_FPM": "gmail", "DEFAULT_BU": "gmail", "DEFAULT_CEO": "gmail"}


def profile(role):
    return os.path.join(ROOT, f".mailbox_profile_{role}")


def available(role):
    return role in PROVIDER and os.path.isdir(profile(role)) and bool(os.listdir(profile(role)))


def fetch_emails(role, quote_no, timeout=120, min_count=1, headless=True):
    """All the emails whose subject or body has the quote number, oldest first. Waits until min_count of them are there or the timeout (seconds) runs out. Runs in its own process (the test session already has a Playwright loop)."""
    if not available(role):
        return None
    headless = headless and PROVIDER[role] == "gmail"      # Outlook on the web only works in a visible window
    r = subprocess.run([sys.executable, "-m", "shared.utils.mailbox", role, quote_no, str(timeout), str(min_count), "1" if headless else "0"],
                       cwd=ROOT, capture_output=True, text=True, timeout=timeout + 120)
    lines = [l for l in r.stdout.splitlines() if l.startswith("{") or l.startswith("[") or l == "null"]
    return json.loads(lines[-1]) if lines else None


def _open(playwright, role, headless):
    return playwright.chromium.launch_persistent_context(profile(role), channel="chrome", headless=headless, ignore_default_args=["--enable-automation"],
                                                args=["--disable-blink-features=AutomationControlled"])


def _gmail(page, quote_no):
    """Every conversation row of the search; each one is expanded and all its messages are read. Returns (signed_in, emails)."""
    page.goto(f"https://mail.google.com/mail/u/0/#search/{quote_no}", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    if "accounts.google.com" in page.url:
        return False, []
    emails = []
    n = page.locator("tr.zA").count()
    for i in range(n):
        page.goto(f"https://mail.google.com/mail/u/0/#search/{quote_no}", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.locator("tr.zA").nth(i).click()
        page.wait_for_timeout(3500)
        page.keyboard.press(";")                          # expand all the messages of the conversation
        page.wait_for_timeout(2000)
        subject = page.locator("h2.hP").first.inner_text()
        bodies = page.locator("div.a3s.aiL").all_inner_texts()
        senders = page.locator("span.gD").evaluate_all("els => els.map(e => e.getAttribute('email'))")
        for j, b in enumerate(bodies):
            links = page.locator("div.a3s.aiL").nth(j).locator("a[href]").evaluate_all("els => els.map(e => e.href)")
            emails.append({"subject": subject, "sender": senders[j] if j < len(senders) else "", "body": b, "links": links})
    return True, emails


def _outlook(page, quote_no):
    """Outlook on the web (Spanish or English interface). Verified 2026-11-13 with the AM mailbox: it needs a visible window (headless sends the login page)."""
    page.goto("https://outlook.office.com/mail/", wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    if "login.microsoftonline.com" in page.url or "login.live.com" in page.url:
        return False, []
    page.locator("input[placeholder='Buscar'], input[placeholder='Search']").first.click()
    page.keyboard.type(quote_no)
    page.keyboard.press("Enter")
    page.wait_for_timeout(6000)
    emails = []
    items = page.locator("[role='option'][data-convid]")
    for i in range(items.count()):
        item = items.nth(i)
        lines = [l for l in item.inner_text().splitlines() if l.strip()]
        subject = next((l for l in lines if l.startswith("OmniOps")), lines[1] if len(lines) > 1 else "")
        item.click()
        body = ""
        for _ in range(12):                                   # the reading pane can take a few seconds to show the body of the email just clicked
            page.wait_for_timeout(1500)
            body = page.locator("[role='document']").first.inner_text() if page.locator("[role='document']").count() else ""
            if quote_no in body:
                break
        links = page.locator("[role='document']").first.locator("a[href]").evaluate_all("els => els.map(e => e.href)")
        emails.append({"subject": subject, "sender": lines[0] if lines else "", "body": body, "links": links})
    return True, emails


def _read(role, quote_no, timeout, min_count, headless):
    from playwright.sync_api import sync_playwright
    deadline = time.time() + timeout
    with sync_playwright() as p:
        ctx = _open(p, role, headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            read = _gmail if PROVIDER[role] == "gmail" else _outlook
            emails = []
            first = True
            while time.time() < deadline:
                if not first:
                    page.reload(wait_until="domcontentloaded")      # Gmail does not redo a search when only the # of the address is the same
                first = False
                ok, emails = read(page, quote_no)
                if not ok:
                    return None                             # the session is gone: a person has to sign in again
                if len(emails) >= min_count:
                    break
                page.wait_for_timeout(5000)
            return [m for m in reversed(emails) if quote_no in m["subject"] or quote_no in m["body"]]    # both list the newest first; a search can also return emails of similar numbers
        finally:
            ctx.close()


if __name__ == "__main__":
    print(json.dumps(_read(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5] == "1")))
