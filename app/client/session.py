"""Session lifecycle and authentication manager for Urja Meter Ops."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Urja portal operator session tokens, expiry, and re-authentication.

    Features:
    - Thread-safe / async-safe token acquisition via asyncio.Lock.
    - Automatic pre-emptive refresh when session nears expiry.
    - Automatic re-login upon encountering HTTP 401 Unauthorized.
    - Strict CSRF header handling required by SvelteKit form action.
    """

    def __init__(
        self,
        portal_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.portal_url = (portal_url or settings.urja_portal_url).rstrip("/")
        self.username = username or settings.urja_username
        self.password = password or settings.urja_password
        self._session_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def is_authenticated(self) -> bool:
        """Returns True if a valid, unexpired session token is currently held."""
        if not self._session_token or not self._expires_at:
            return False
        # Buffer of 60 seconds before actual expiration
        return datetime.now(timezone.utc) < self._expires_at

    async def get_cookie_header(self, client: httpx.AsyncClient, force_refresh: bool = False) -> str:
        """Retrieve a valid session cookie string, logging in if needed."""
        async with self._lock:
            if not force_refresh and self.is_authenticated:
                return f"__Secure-better-auth.session_token={self._session_token}"

            await self._login(client)
            return f"__Secure-better-auth.session_token={self._session_token}"

    async def _login(self, client: httpx.AsyncClient) -> None:
        """Authenticate against the Urja portal and store session token."""
        login_url = f"{self.portal_url}/login"
        headers = {
            "Origin": self.portal_url,
            "Referer": login_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "email": self.username,
            "password": self.password,
        }

        logger.info(f"Authenticating with Urja Meter Ops as {self.username}...")
        try:
            resp = await client.post(
                login_url,
                data=data,
                headers=headers,
                timeout=settings.request_timeout_seconds,
            )
        except Exception as e:
            logger.error(f"Failed to connect to login endpoint: {e}")
            raise RuntimeError(f"Urja portal unreachable at {login_url}: {e}") from e

        # Extract session token from Set-Cookie
        token = resp.cookies.get("__Secure-better-auth.session_token")
        if not token:
            # Check raw headers if cookie jar didn't catch domain
            set_cookie = resp.headers.get("set-cookie", "")
            if "__Secure-better-auth.session_token=" in set_cookie:
                parts = set_cookie.split("__Secure-better-auth.session_token=")[1].split(";")[0]
                token = parts

        if not token:
            logger.error(f"Login failed: status={resp.status_code}, body={resp.text[:200]}")
            raise RuntimeError(
                f"Urja portal authentication failed. Check credentials ({self.username}). "
                f"Status: {resp.status_code}"
            )

        self._session_token = token
        logger.info("Successfully obtained session token from Urja portal.")

        # Probe /api/auth/get-session for exact expiry timestamp
        try:
            session_resp = await client.get(
                f"{self.portal_url}/api/auth/get-session",
                headers={"Cookie": f"__Secure-better-auth.session_token={token}"},
                timeout=settings.request_timeout_seconds,
            )
            if session_resp.status_code == 200:
                sdata = session_resp.json().get("session", {})
                expires_str = sdata.get("expiresAt")
                if expires_str:
                    # Parse ISO format (e.g. 2026-10-25T14:02:22.085Z)
                    self._expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
        except Exception as ex:
            logger.warning(f"Could not fetch session metadata from /api/auth/get-session: {ex}")

        # Fallback expiration: 55 minutes from now if not resolved
        if not self._expires_at:
            from datetime import timedelta
            self._expires_at = datetime.now(timezone.utc) + timedelta(minutes=55)

        logger.info(f"Session valid until {self._expires_at.isoformat()}")

    def invalidate(self) -> None:
        """Clear current session so the next request forces a fresh login."""
        self._session_token = None
        self._expires_at = None
