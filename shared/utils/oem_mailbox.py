"""Reads the OEM test mailbox in a browser profile that a person signed in ONCE, so the OEM decision links can be taken from the email without a password or an app password
(Google does not let this account turn on 2-step verification, so IMAP is not possible).

  python tools/oem_mailbox_login.py     one time: opens Chrome on the profile folder; sign in to the mailbox, then close Chrome.
  fetch_decision_link(quote_no, nth)    the link of a button of the nth email 'OmniOps: Quotation <no>: awaiting your review' (1 = the first one sent).

The profile folder (.oem_mailbox_profile) holds the session of the test mailbox: it is ignored by git and must never be shared. Returns None when the profile does not exist or the mailbox cannot be read,
so the caller can fall back to asking a person."""
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILE = os.path.join(ROOT, ".oem_mailbox_profile")
LINK = re.compile(r"/api/oem-decision/")


def available():
    return os.path.isdir(PROFILE) and bool(os.listdir(PROFILE))


def _clean(href):
    """Gmail may wrap the link in https://www.google.com/url?q=<real link>."""
    if "google.com/url" in href:
        q = parse_qs(urlparse(href).query).get("q")
        if q:
            return unquote(q[0])
    return href


def fetch_decision_link(quote_no, nth=1, timeout=120, headless=True):
    """The decision link of the nth email of that quotation (1 = the oldest). Runs in its own process because the test session already has a Playwright loop."""
    if not available():
        return None
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "shared.utils.oem_mailbox", quote_no, str(nth), str(timeout), "1" if headless else "0"], cwd=ROOT, capture_output=True, text=True, timeout=timeout + 90)
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("http")]
    return lines[-1] if lines else None


def fetch_email(quote_no, nth=1, timeout=150, headless=True):
    """{'sender': ..., 'subject': ..., 'body': ...} of the nth email (1 = the oldest) of that quotation, or None."""
    if not available():
        return None
    import json
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "shared.utils.oem_mailbox", quote_no, str(nth), str(timeout), "1" if headless else "0", "text"], cwd=ROOT, capture_output=True, text=True, timeout=timeout + 90)
    lines = [l for l in r.stdout.splitlines() if l.startswith("{")]
    return json.loads(lines[-1]) if lines else None


def _fetch(quote_no, nth=1, timeout=120, headless=True, want="link"):
    """Polls the mailbox until the email is there or the timeout (seconds) runs out."""
    from playwright.sync_api import sync_playwright
    deadline = time.time() + timeout
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=headless, ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"])
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            first = True
            while time.time() < deadline:
                page.goto(f"https://mail.google.com/mail/u/0/#search/{quote_no}", wait_until="domcontentloaded")
                if not first:
                    page.reload(wait_until="domcontentloaded")      # Gmail does not redo the search when only the # of the address is the same: without this a late email is never seen
                first = False
                page.wait_for_timeout(5000)
                if "accounts.google.com" in page.url:
                    return None                       # the session is gone: a person has to sign in again
                rows = page.locator("tr.zA")          # Gmail groups emails with the same subject in ONE conversation row
                if rows.count():
                    rows.first.click()
                    page.wait_for_timeout(4000)
                    page.keyboard.press(";")          # expand all the messages of the conversation
                    page.wait_for_timeout(2500)
                    tokens = {}
                    for h in page.locator("a[href]").evaluate_all("els => els.map(e => e.href)"):
                        h = _clean(h)
                        if LINK.search(h):
                            tokens.setdefault(h.split("?")[0], h)   # one entry per email (per token), in the order they appear: the oldest first
                    if want == "text":
                        bodies = page.locator("div.a3s.aiL").all_inner_texts()
                        senders = page.locator("span.gD").evaluate_all("els => els.map(e => e.getAttribute('email'))")
                        if len(bodies) >= nth and len(tokens) >= nth:
                            return {"sender": senders[nth - 1] if len(senders) >= nth else "", "subject": page.locator("h2.hP").first.inner_text(), "body": bodies[nth - 1]}
                    elif len(tokens) >= nth:
                        return list(tokens.values())[nth - 1]
                page.wait_for_timeout(5000)
            return None
        finally:
            ctx.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 5 and sys.argv[5] == "text":
        import json
        print(json.dumps(_fetch(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1", "text")))
    else:
        print(_fetch(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1") or "")
