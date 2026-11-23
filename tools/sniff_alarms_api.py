"""sniff_alarms_api — discovers the alarms API by capturing network traffic.
Opens /alarms logged in and dumps calls whose URL mentions alarm/alert/events.
Investigation tool (tools/). Not a test.
    python -m tools.sniff_alarms_api
"""
from __future__ import annotations

import json
import time

from shared.config.settings import BASE_URL, ALARMS_UI_PATH
from shared.config.credentials import load_credentials
from framework_ui.browser.browser_factory import BrowserFactory
from framework_ui.pages.auth.login_page import LoginPage


def _is_interesting(url):
    u = url.lower()
    return "alarm" in u or "alert" in u or "/events/" in u


def sniff(seconds=8):
    captures = []
    creds = load_credentials()
    factory = BrowserFactory(headless=False)
    page = factory.__enter__()

    def on_response(resp):
        try:
            if _is_interesting(resp.url):
                body = None
                try:
                    body = resp.text()
                except Exception:
                    pass
                captures.append((resp.request.method, resp.url, resp.status, body))
        except Exception:
            pass

    try:
        LoginPage(page).login(creds["email"], creds["password"])
        page.on("response", on_response)
        page.goto(BASE_URL + ALARMS_UI_PATH)
        time.sleep(seconds)
    finally:
        factory.__exit__(None, None, None)

    if not captures:
        print("Didn't capture any calls with alarm/alert/events. Was the table visible?")
        return
    for method, url, status, body in captures:
        print("\n" + "=" * 70)
        print(f"{method} {url}\nstatus: {status}")
        if body:
            try:
                print(json.dumps(json.loads(body), indent=2, ensure_ascii=False)[:1800])
            except Exception:
                print(body[:600])


if __name__ == "__main__":
    sniff()
