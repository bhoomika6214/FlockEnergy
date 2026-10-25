"""Unit tests for UrjaClient HMAC signing, timestamping, and session handling."""

import hashlib
import hmac
import time
import pytest
from app.client.urja_client import UrjaClient
from app.client.session import SessionManager


def test_hmac_signature_calculation():
    """Verify HMAC-SHA256 signature conforms to portal specification."""
    client = UrjaClient()
    secret = "test_signing_secret_12345"
    method = "GET"
    path = "/portal/export"
    query_string = "page=1"

    timestamp, signature = client.sign_request(method, path, query_string, secret)

    # Expected format: METHOD\nPATH\nQUERYSTRING\nTIMESTAMP
    expected_payload = f"{method}\n{path}\n{query_string}\n{timestamp}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), expected_payload, hashlib.sha256).hexdigest()

    assert signature == expected_sig
    assert len(signature) == 64  # SHA-256 hex string length
    assert int(timestamp) <= int(time.time())


def test_session_manager_initial_state():
    """Verify session manager starts unauthenticated until login."""
    session = SessionManager(
        portal_url="https://urja-ops.flockenergy.tech",
        username="operator@urja.local",
        password="test-password",
    )
    assert not session.is_authenticated
    session.invalidate()
    assert not session.is_authenticated
