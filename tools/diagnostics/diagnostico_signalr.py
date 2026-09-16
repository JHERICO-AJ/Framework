"""
diagnostico_signalr.py — does the on-screen number update by itself (SignalR)?

Opens the dashboard with Playwright, and for ~20s reads the value WITHOUT
reloading, to see if it changes on its own (a sign that SignalR is updating
live).

Run:  python diagnostico_signalr.py
"""

import time

from framework_ui.pages.monitoring.monitoring_page import MonitoringPage

DURATION_S = 20

print("Opening browser (visible) and logging in...")
ui = UiSession(headless=False)   # visible, so you can see the page
print(f"Ready. Watching the value for {DURATION_S}s WITHOUT reloading...\n")

values = []
t0 = time.time()
try:
    while time.time() - t0 < DURATION_S:
        val, txt = ui.read()          # direct read, without reloading
        stamp = time.strftime("%H:%M:%S")
        print(f"  [{stamp}]  {txt}")
        values.append(val)
        time.sleep(2)
finally:
    distinct = len(set(v for v in values if v is not None))
    print("\n=== DIAGNOSIS ===")
    if distinct > 1:
        print(f"The value CHANGED on its own ({distinct} distinct values).")
        print("=> SignalR DOES update the screen live. We can go without reloading.")
    else:
        print("The value did NOT change (stayed fixed).")
        print("=> SignalR isn't updating this browser. We'd need to see why,")
        print("   or stick with the reload mode (which still validates the data fine).")
    ui.close()
