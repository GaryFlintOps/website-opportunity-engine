"""
auth.py — Simple single-admin password protection for the dashboard.

Usage:
  from src.auth import require_auth

  @app.get("/")
  async def index(request: Request):
      require_auth(request)
      ...

Configuration:
  Set the ADMIN_PASSWORD environment variable (e.g. in Render → Environment).
  If ADMIN_PASSWORD is not set the app boots with auth DISABLED and logs a warning
  on startup — safe for local dev, never acceptable in production.

Session mechanism:
  • Login POST sets an httponly cookie: session=<ADMIN_PASSWORD>
  • Every protected route checks that cookie against the env var.
  • No JWTs, no DB — intentionally minimal.
"""

import os
from fastapi import Request

# Read once at import time; Render injects this via the Environment tab.
ADMIN_PASSWORD: str | None = os.getenv("ADMIN_PASSWORD")

# Cookie name — change here if you need a different name
_COOKIE_NAME = "session"


class AuthRequired(Exception):
    """
    Raised by require_auth() when a request lacks a valid session cookie.

    Caught by the app-level exception handler registered in dashboard.py,
    which converts it into a 302 redirect to /login.
    """
    pass


def require_auth(request: Request) -> None:
    """
    Raise AuthRequired if the request has no valid session cookie.

    Call this at the very start of every protected route handler:
        require_auth(request)

    The app-level @app.exception_handler(AuthRequired) in dashboard.py
    converts it into a RedirectResponse to /login automatically.
    """
    if not ADMIN_PASSWORD:
        # Auth intentionally disabled when env var is absent (local dev only).
        return

    session = request.cookies.get(_COOKIE_NAME)
    if session != ADMIN_PASSWORD:
        raise AuthRequired()


def auth_enabled() -> bool:
    """Return True when ADMIN_PASSWORD is configured."""
    return bool(ADMIN_PASSWORD)
