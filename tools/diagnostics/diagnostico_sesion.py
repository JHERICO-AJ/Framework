"""
diagnostico_sesion.py — how long does the browser session last before expiring?

Logs in, goes to the dashboard, and every 2s says which page it's on (dashboard
vs login). This way we see if the session expires quickly and why the monitor
was losing the screen.

Run:  python diagnostico_sesion.py
"""

import re
import time

from playwright.sync_api import sync_playwright
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

creds = _load_creds()
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()

print("Login...")
page.goto(LOGIN_URL)
page.locator("#loginUser").fill(creds["email"])
page.locator("#loginPassword").fill(creds["password"])
page.locator("button.login-submit-button").click()
page.wait_for_load_state("networkidle", timeout=15000)
print(f"After login I'm at: {page.url}")

page.goto(MONITORING_URL)
print("Went to the dashboard. Watching the URL every 2s...\n")

t0 = time.time()
try:
    for _ in range(30):   # ~60s
        url = page.url
        seg = time.time() - t0
        on_login = "login" in url
        state = "ON LOGIN (session lost)" if on_login else "on dashboard OK"
        print(f"  {seg:5.0f}s  {state}   ({url})")
        if on_login:
            print("\n=> The session expired / wasn't kept. That's the problem to solve.")
            break
        time.sleep(2)
    else:
        print("\n=> The session stayed stable. The problem was something else.")
finally:
    for step in (browser.close, pw.stop):
        try:
            step()
        except Exception:
            pass
