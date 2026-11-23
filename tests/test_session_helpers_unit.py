"""Proves unitàries dels càlculs i la resposta d'expiració de sessió."""
from datetime import UTC, datetime
import unittest

from app.api.deps import expired_session_exception
from app.core.security import SESSION_COOKIE
from app.model_registry import load_models
from app.models.session import SESSION_IDLE_TIMEOUT, UserSession, new_expiry


class SessionExpiryTest(unittest.TestCase):
    def test_new_expiry_is_one_idle_timeout_from_now(self):
        before = datetime.now(UTC)
        expiry = new_expiry()
        after = datetime.now(UTC)

        self.assertGreaterEqual(expiry, before + SESSION_IDLE_TIMEOUT)
        self.assertLessEqual(expiry, after + SESSION_IDLE_TIMEOUT)

    def test_touch_replaces_the_existing_expiry(self):
        load_models()
        session = UserSession(
            token="a" * 64,
            user_id=1,
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        before = datetime.now(UTC)

        session.touch()

        self.assertGreaterEqual(session.expires_at, before + SESSION_IDLE_TIMEOUT)


class ExpiredSessionResponseTest(unittest.TestCase):
    def test_expired_session_clears_the_secure_http_only_cookie(self):
        exception = expired_session_exception()
        cookie = exception.headers["Set-Cookie"].lower()

        self.assertEqual(exception.status_code, 401)
        self.assertEqual(exception.detail, "Invalid or missing session")
        self.assertIn(f"{SESSION_COOKIE}=\"\"", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("secure", cookie)


if __name__ == "__main__":
    unittest.main()
