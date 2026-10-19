"""Register, login and session validation against an isolated, freshly migrated database."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.security import SESSION_COOKIE, generate_session_token, hash_session_token
from app.database import engine, get_db
from app.main import app
from app.models.session import SESSION_IDLE_TIMEOUT, UserSession
from app.models.user import User


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "auth_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        cls.isolated = create_engine(engine.url.set(database=cls.database))
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        cls.Session = sessionmaker(bind=cls.isolated, autoflush=False, expire_on_commit=False)

        def override_get_db():
            with cls.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def setUp(self):
        # A fresh cookie jar per test. HTTPS, because the client only sends Secure cookies over it.
        self.client = TestClient(app, base_url="https://testserver")

    def register(self, email, password="correct-horse"):
        return self.client.post("/api/auth/register", json={"email": email, "password": password})

    def login(self, email, password="correct-horse"):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def me(self, token=None):
        headers = {"Cookie": f"{SESSION_COOKIE}={token}"} if token else None
        return self.client.get("/api/auth/me", headers=headers)

    def new_email(self):
        return f"{uuid4().hex}@example.com"

    def sessions_of(self, email):
        with self.Session() as db:
            user_id = db.scalar(select(User.id).where(User.email == email))
            return db.scalars(select(UserSession).where(UserSession.user_id == user_id)).all()

    def assert_about(self, actual, expected):
        self.assertLess(abs(actual - expected), timedelta(seconds=5))

    def test_register_login_and_me(self):
        response = self.register("Ana@Example.com")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["email"], "ana@example.com")
        self.assertNotIn("password", body)
        self.assertNotIn("hashed_password", body)

        response = self.login("ana@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "ana@example.com")

        # The client sends the cookie back on its own.
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "ana@example.com")

    def test_login_creates_session_and_sets_secure_cookie(self):
        email = self.new_email()
        self.register(email)
        response = self.login(email)

        cookie = response.headers["set-cookie"].lower()
        self.assertTrue(cookie.startswith(f"{SESSION_COOKIE}="))
        for attribute in ("httponly", "secure", "samesite=lax"):
            self.assertIn(attribute, cookie)

        token = response.cookies[SESSION_COOKIE]
        [session] = self.sessions_of(email)
        self.assertEqual(session.token, hash_session_token(token))
        self.assertNotEqual(session.token, token)
        self.assert_about(session.expires_at, datetime.now(UTC) + SESSION_IDLE_TIMEOUT)

    def test_token_never_appears_in_url_or_body(self):
        email = self.new_email()
        self.register(email)
        response = self.login(email)
        token = response.cookies[SESSION_COOKIE]
        self.assertNotIn("location", response.headers)
        self.assertNotIn(token, str(response.url))
        self.assertNotIn(token, response.text)

    def test_each_login_gets_a_different_token(self):
        email = self.new_email()
        self.register(email)
        first = self.login(email).cookies[SESSION_COOKIE]
        second = self.login(email).cookies[SESSION_COOKIE]
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.sessions_of(email)), 2)

    def test_duplicate_email_is_rejected(self):
        self.assertEqual(self.register("dup@example.com").status_code, 201)
        self.assertEqual(self.register("DUP@example.com").status_code, 409)

    def test_invalid_registration_data(self):
        self.assertEqual(self.register("not-an-email").status_code, 422)
        self.assertEqual(self.register("short@example.com", "1234567").status_code, 422)

    def test_failed_login_creates_no_session_or_cookie(self):
        email = self.new_email()
        self.register(email)
        response = self.login(email, "wrong-password")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(self.sessions_of(email), [])
        self.assertEqual(self.login("nobody@example.com").status_code, 401)

    def test_login_rejects_password_longer_than_72_characters(self):
        response = self.login("nobody@example.com", "a" * 73)
        self.assertEqual(response.status_code, 422)

    def test_missing_or_invalid_token_is_unauthorized(self):
        self.assertEqual(self.me().status_code, 401)
        self.assertEqual(self.me(generate_session_token()).status_code, 401)

    def test_expired_session_is_unauthorized(self):
        email = self.new_email()
        self.register(email)
        token = self.login(email).cookies[SESSION_COOKIE]
        with self.Session() as db:
            db.execute(
                UserSession.__table__.update()
                .where(UserSession.token == hash_session_token(token))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            db.commit()
        self.assertEqual(self.me(token).status_code, 401)

    def test_valid_request_renews_expiry_to_now_plus_60_minutes(self):
        email = self.new_email()
        self.register(email)
        token = self.login(email).cookies[SESSION_COOKIE]
        with self.Session() as db:
            db.execute(
                UserSession.__table__.update()
                .where(UserSession.token == hash_session_token(token))
                .values(expires_at=datetime.now(UTC) + timedelta(minutes=5))
            )
            db.commit()

        self.assertEqual(self.me(token).status_code, 200)
        [session] = self.sessions_of(email)
        self.assert_about(session.expires_at, datetime.now(UTC) + SESSION_IDLE_TIMEOUT)

    def test_session_of_deleted_user_is_unauthorized(self):
        email = self.new_email()
        self.register(email)
        token = self.login(email).cookies[SESSION_COOKIE]
        with self.Session() as db:
            db.delete(db.scalar(select(User).where(User.email == email)))
            db.commit()
        self.assertEqual(self.me(token).status_code, 401)


if __name__ == "__main__":
    unittest.main()
