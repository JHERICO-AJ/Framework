"""One-time sign-in of the OEM test mailbox for the automatic reading of the decision links (see shared/utils/oem_mailbox.py).
It opens your own Chrome (no automation flags, so Google lets you sign in) on the folder .oem_mailbox_profile. Sign in to the test mailbox, open the inbox, and close Chrome.
Usage: python tools/oem_mailbox_login.py"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.utils.oem_mailbox import PROFILE  # noqa: E402

CANDIDATES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
chrome = shutil.which("chrome") or next((c for c in CANDIDATES if os.path.exists(c)), None)
if not chrome:
    sys.exit("Chrome was not found.")
os.makedirs(PROFILE, exist_ok=True)
print("Chrome opens on its own profile. Sign in to the OEM test mailbox, open the inbox and close Chrome.")
subprocess.run([chrome, f"--user-data-dir={PROFILE}", "--no-first-run", "https://mail.google.com/"])
print("Profile saved in", PROFILE)
