"""Login selectors. Strings ONLY, zero logic.

OmniOps' /login page shows BOTH options (confirmed 2026-08-28):
  - Native email/password fields, submitted directly on that page.
  - A "Sign in with Microsoft" button, which redirects to Microsoft's
    identity platform (login.microsoftonline.com) -- a TWO-STEP form
    (email screen -> Next -> password screen -> Sign in -> optional "Stay
    signed in?" prompt) before redirecting back to OmniOps.

See login_page.py -- LOGIN_METHOD picks which of the two login() uses.

The Microsoft-side ids below (i0116/i0118/idSIButton9/idBtn_Back) are
Microsoft's own stable field ids for the identity platform, not something
OmniOps controls -- these don't change per OmniOps deploy.
"""

# --- OmniOps' own /login page: native form ---
EMAIL_INPUT = "input[type='email'], input[name='email']"
PASSWORD_INPUT = "input[type='password']"
SUBMIT_BUTTON = "button[type='submit']"

# --- OmniOps' own /login page: Microsoft SSO entry point ---
MS_SIGNIN_BUTTON = "button:has-text('Microsoft'), a:has-text('Microsoft')"

# --- Microsoft identity platform (login.microsoftonline.com) ---
MS_EMAIL_INPUT = "#i0116"
MS_NEXT_BUTTON = "#idSIButton9"
MS_PASSWORD_INPUT = "#i0118"
MS_SIGNIN_SUBMIT = "#idSIButton9"          # same id as Next -- reused per step
MS_STAY_SIGNED_IN_NO = "#idBtn_Back"       # "Stay signed in?" prompt, if it appears
