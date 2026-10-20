"""Sessions table against an isolated, freshly migrated database."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models.session import SESSION_IDLE_TIMEOUT, UserSession
from app.models.user import User


class SessionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "sessions_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        cls.isolated = create_engine(engine.url.set(database=cls.database))
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        cls.Session = sessionmaker(bind=cls.isolated, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def create_user(self, db):
        user = User(email=f"{uuid4().hex}@example.com", hashed_password="x" * 60)
        db.add(user)
        db.commit()
        return user

    def assert_about(self, actual, expected):
        self.assertLess(abs(actual - expected), timedelta(seconds=5))

    def test_table_has_unique_index_on_token(self):
        columns = {c["name"] for c in inspect(self.isolated).get_columns("sessions")}
        self.assertTrue({"token", "user_id", "created_at", "expires_at"} <= columns)
        indexes = {i["name"]: i for i in inspect(self.isolated).get_indexes("sessions")}
        self.assertEqual(indexes["ix_sessions_token"]["column_names"], ["token"])
        self.assertTrue(indexes["ix_sessions_token"]["unique"])

    def test_duplicate_token_is_rejected(self):
        with self.Session() as db:
            user = self.create_user(db)
            db.add(UserSession(token="duplicate", user_id=user.id))
            db.commit()
            db.add(UserSession(token="duplicate", user_id=user.id))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_new_session_expires_in_60_minutes(self):
        with self.Session() as db:
            user = self.create_user(db)
            session = UserSession(token=uuid4().hex, user_id=user.id)
            db.add(session)
            db.commit()
            db.refresh(session)
            self.assert_about(session.expires_at, session.created_at + SESSION_IDLE_TIMEOUT)

    def test_touch_moves_expiry_to_last_request_plus_60_minutes(self):
        with self.Session() as db:
            user = self.create_user(db)
            session = UserSession(
                token=uuid4().hex, user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            db.add(session)
            db.commit()
            session.touch()
            db.commit()
            db.refresh(session)
            self.assert_about(session.expires_at, datetime.now(UTC) + SESSION_IDLE_TIMEOUT)

    def test_sessions_are_deleted_with_their_user(self):
        with self.Session() as db:
            user = self.create_user(db)
            db.add(UserSession(token=uuid4().hex, user_id=user.id))
            db.commit()
            db.delete(user)
            db.commit()
            remaining = db.scalar(text("SELECT count(*) FROM sessions WHERE user_id = :id"), {"id": user.id})
            self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
