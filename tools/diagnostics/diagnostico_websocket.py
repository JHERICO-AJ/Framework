"""
diagnostico_websocket.py — why isn't SignalR updating the Playwright browser?

Listens, for ~25s, to what happens inside the browser:
  - WebSockets that open (SignalR uses WebSocket for real time)
  - browser console errors
  - network requests that fail (especially ones mentioning 'hub' or 'negotiate')

With that we can see if SignalR tries to connect and fails, or doesn't even try.

Run:  python diagnostico_websocket.py
"""

import time

from playwright.sync_api import sync_playwright
from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

events = {"ws": [], "console_err": [], "req_fail": []}

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()

# --- spies ---
def on_ws(ws):
    events["ws"].append(ws.url)
    print(f"  [WebSocket OPENED] {ws.url}")
    ws.on("close", lambda: print(f"  [WebSocket CLOSED] {ws.url}"))
    ws.on("socketerror", lambda e: print(f"  [WebSocket ERROR] {ws.url}"))

page.on("websocket", on_ws)
page.on("console", lambda m: (events["console_err"].append(m.text)
         or print(f"  [CONSOLE {m.type}] {m.text[:160]}")) if m.type in ("error", "warning") else None)
page.on("requestfailed", lambda r: (events["req_fail"].append(r.url)
         or print(f"  [REQUEST FAILED] {r.url}  ({r.failure})")))

# --- login + dashboard ---
creds = _load_creds()
print("Login...")
page.goto(LOGIN_URL)
page.locator("#loginUser").fill(creds["email"])
page.locator("#loginPassword").fill(creds["password"])
page.locator("button.login-submit-button").click()
page.wait_for_load_state("networkidle", timeout=15000)
for _ in range(5):
    page.goto(MONITORING_URL)
    page.wait_for_load_state("networkidle", timeout=15000)
    if "login" not in page.url:
        break
    time.sleep(2)

print(f"\nOn the dashboard ({page.url}). Listening for 25s...\n")
time.sleep(25)

print("\n=== SUMMARY ===")
print(f"WebSockets opened   : {len(events['ws'])}")
for u in events["ws"]:
    print(f"    {u}")
print(f"Console errors       : {len(events['console_err'])}")
print(f"Failed requests       : {len(events['req_fail'])}")
hub = [u for u in events["ws"] + events["req_fail"] if "hub" in u.lower() or "negotiate" in u.lower()]
print("\nRelated to SignalR (hub/negotiate):")
for u in hub:
    print(f"    {u}")
if not events["ws"]:
    print("\n=> NO WebSocket was opened. SignalR didn't even try to connect in this browser.")
elif hub:
    print("\n=> SignalR tried (there's a hub/negotiate). Check it above: it may have failed.")

for step in (browser.close, pw.stop):
    try:
        step()
    except Exception:
        pass
