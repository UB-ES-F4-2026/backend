"""Wallet balance endpoint against an isolated, freshly migrated database."""
import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.security import SESSION_COOKIE, generate_session_token, hash_session_token
from app.database import engine, get_db
from app.main import app
from app.models.session import UserSession
from app.models.user import User
from app.models.wallet import Wallet


class WalletBalanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "wallet_balance_test_" + uuid4().hex
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
        self.client = TestClient(app, base_url="https://testserver")
        with self.Session() as db:
            user = User(
                email=f"{uuid4().hex}@example.com",
                first_name="Test",
                last_name="User",
                phone="+34612345678",
                hashed_password="x" * 60,
                wallet=Wallet(available_cents=12345),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            token = generate_session_token()
            db.add(UserSession(token=hash_session_token(token), user_id=user.id))
            db.commit()
            self.user_id = user.id
            self.cookie = f"{SESSION_COOKIE}={token}"

    def test_requires_an_active_session(self):
        response = self.client.get("/api/me/wallet")

        self.assertEqual(response.status_code, 401)

    def test_repeated_reads_return_balance_without_mutating_wallet(self):
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            original_balance = wallet.available_cents
            original_updated_at = wallet.updated_at

        headers = {"Cookie": self.cookie}
        first = self.client.get("/api/me/wallet", headers=headers)
        second = self.client.get("/api/me/wallet", headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), {"available_cents": 12345, "currency": "eur"})
        self.assertEqual(second.json(), first.json())

        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            wallet_count = db.scalar(select(func.count()).select_from(Wallet))
            self.assertEqual(wallet.available_cents, original_balance)
            self.assertEqual(wallet.updated_at, original_updated_at)
            self.assertEqual(wallet_count, 1)


if __name__ == "__main__":
    unittest.main()