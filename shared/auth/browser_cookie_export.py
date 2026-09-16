"""browser_cookie_export.py — bridges a real Microsoft SSO browser login
(framework_ui.pages.auth.login_page.LoginPage) to CookieAuth's expected
input file ('omniops_cookie.txt', MODE 2 -- see cookie_auth.py).

Previously CookieAuth required a human to copy the cookie out of DevTools
by hand. Since we already automate the full SSO popup login for UI tests
(2026-08-28), this does the same login and writes the cookie header
automatically -- no manual step, and it stays fresh every session since
it's regenerated at the start of each test run rather than a stale
hand-copied value.
"""
from __future__ import annotations


def cookie_header_from_context(context, domain_substring):
    """Builds a 'name1=value1; name2=value2' Cookie header string from every
    cookie in this browser context whose domain matches domain_substring
    (so we don't leak unrelated login.microsoftonline.com session cookies
    into a header meant for the OmniOps origin)."""
    cookies = context.cookies()
    relevant = [c for c in cookies if domain_substring in c["domain"]]
    return "; ".join(f"{c['name']}={c['value']}" for c in relevant)


def write_cookie_file(context, domain_substring, cookie_path="omniops_cookie.txt"):
    header = cookie_header_from_context(context, domain_substring)
    if not header:
        raise ValueError(
            f"no cookies found for domain containing {domain_substring!r} -- "
            "was the browser actually logged in when this was called?")
    with open(cookie_path, "w", encoding="utf-8") as f:
        f.write(header)
    return cookie_path
