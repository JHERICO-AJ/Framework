"""One-time sign-in of a test mailbox for the automatic reading of notification emails (see shared/utils/mailbox.py).
It opens your own Chrome (no automation flags, so Google and Microsoft let you sign in) on the role's profile folder. Sign in, open the inbox, and close Chrome.
Usage: python tools/mailbox_login.py <AM|FPM|BU|CEO|DEFAULT_FPM|DEFAULT_BU|DEFAULT_CEO>"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.utils.mailbox import PROVIDER, profile  # noqa: E402

CANDIDATES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
role = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
if role not in PROVIDER:
    sys.exit(f"Usage: python tools/mailbox_login.py <{'|'.join(PROVIDER)}>")
chrome = shutil.which("chrome") or next((c for c in CANDIDATES if os.path.exists(c)), None)
if not chrome:
    sys.exit("Chrome was not found.")
os.makedirs(profile(role), exist_ok=True)
url = "https://mail.google.com/" if PROVIDER[role] == "gmail" else "https://outlook.office.com/mail/"
print(f"Chrome opens on the {role} profile. Sign in to that mailbox, open the inbox and close Chrome.")
subprocess.run([chrome, f"--user-data-dir={profile(role)}", "--no-first-run", url])
print("Profile saved in", profile(role))
