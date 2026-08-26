"""
diagnostico_token.py — where does the token end up after login, and does it survive?

Logs in and checks where the app stores the token (localStorage, sessionStorage,
cookies). Then navigates to the dashboard and checks again, to see if the token
survived or was lost (which would explain the 401s).

Run:  python diagnostico_token.py
"""

import json
import re
import time

from playwright.sync_api import sync_playwright
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

HINTS = ("token", "jwt", "auth", "bearer", "access", "session")


def is_interesting(key, value):
    txt = f"{key} {value}".lower()
    if any(p in txt for p in HINTS):
        return True
    return isinstance(value, str) and len(value) > 40  # long strings = possible tokens


def dump_storage(page, moment):
    ls = page.evaluate("() => Object.entries(window.localStorage)")
    ss = page.evaluate("() => Object.entries(window.sessionStorage)")
    cookies = page.context.cookies()
    print(f"\n----- {moment} (url: {page.url}) -----")
    print("localStorage:")
    for k, v in ls:
        mark = "  <-- possible token" if is_interesting(k, v) else ""
        print(f"    {k} = {str(v)[:60]}{mark}")
    print("sessionStorage:")
    for k, v in ss:
        mark = "  <-- possible token" if is_interesting(k, v) else ""
        print(f"    {k} = {str(v)[:60]}{mark}")
    print("cookies:")
    for c in cookies:
        mark = "  <-- possible token" if is_interesting(c['name'], c.get('value','')) else ""
        print(f"    {c['name']} = {str(c.get('value',''))[:60]}{mark}")


pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()

creds = _load_creds()
print("Login...")
page.goto(LOGIN_URL)
page.locator("#loginUser").fill(creds["email"])
page.locator("#loginPassword").fill(creds["password"])
page.locator("button.login-submit-button").click()
page.wait_for_load_state("networkidle", timeout=15000)
time.sleep(2)   # give it time to save the token

dump_storage(page, "RIGHT AFTER LOGIN")

print("\nNavigating to the dashboard...")
page.goto(MONITORING_URL)
page.wait_for_load_state("networkidle", timeout=15000)
time.sleep(2)

dump_storage(page, "AFTER GOING TO THE DASHBOARD")
print(f"\n=> Did I end up on the dashboard or on login?  {page.url}")

for step in (browser.close, pw.stop):
    try:
        step()
    except Exception:
        pass
