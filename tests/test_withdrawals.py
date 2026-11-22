"""Simulated wallet withdrawals against an isolated database."""
import threading
import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.security import SESSION_COOKIE, generate_session_token, hash_session_token
from app.core.withdrawals import InsufficientAvailableBalance, withdraw_funds
from app.database import engine, get_db
from app.main import app
from app.models.session import UserSession
from app.models.user import User
from app.models.wallet import Wallet


VALID_IBAN = "ES9121000418450200051332"


class WithdrawalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "withdrawals_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        cls.isolated = create_engine(engine.url.set(database=cls.database))
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        cls.Session = sessionmaker(
            bind=cls.isolated, autoflush=False, expire_on_commit=False
        )

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
            self.headers = {"Cookie": f"{SESSION_COOKIE}={token}"}

    def withdrawal_payload(self, **overrides):
        return {
            "amount_cents": 5000,
            "iban": VALID_IBAN,
            "account_holder": "Ada Lovelace",
            **overrides,
        }

    def test_requires_an_active_session(self):
        response = self.client.post(
            "/api/me/wallet/withdrawals", json=self.withdrawal_payload()
        )

        self.assertEqual(response.status_code, 401)

    def test_withdrawal_returns_confirmation_and_updated_available_balance(self):
        response = self.client.post(
            "/api/me/wallet/withdrawals",
            headers=self.headers,
            json=self.withdrawal_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "amount_cents": 5000,
                "masked_iban": "ES91****************1332",
                "account_holder": "Ada Lovelace",
                "available_cents": 7345,
                "currency": "eur",
            },
        )
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, 7345)

    def test_accepts_the_minimum_withdrawal_of_fifty_cents(self):
        response = self.client.post(
            "/api/me/wallet/withdrawals",
            headers=self.headers,
            json=self.withdrawal_payload(amount_cents=50),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available_cents"], 12295)

    def test_rejects_invalid_request_data_without_changing_the_balance(self):
        invalid_payloads = (
            self.withdrawal_payload(amount_cents=49),
            self.withdrawal_payload(amount_cents=50.0),
            self.withdrawal_payload(iban="ES00INVALID"),
            self.withdrawal_payload(account_holder="   "),
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/me/wallet/withdrawals", headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 422)

        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, 12345)

    def test_rejects_unknown_iban_country_and_invalid_country_length(self):
        invalid_ibans = (
            "ZZ66000000000000000000",
            "ES8200000000000000000",
        )

        for iban in invalid_ibans:
            with self.subTest(iban=iban):
                response = self.client.post(
                    "/api/me/wallet/withdrawals",
                    headers=self.headers,
                    json=self.withdrawal_payload(iban=iban),
                )
                self.assertEqual(response.status_code, 422)

        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, 12345)

    def test_rejects_insufficient_balance_without_changing_the_wallet(self):
        response = self.client.post(
            "/api/me/wallet/withdrawals",
            headers=self.headers,
            json=self.withdrawal_payload(amount_cents=12346),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "Insufficient available balance"})
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, 12345)

    def test_withdrawal_can_use_the_exact_available_balance(self):
        response = self.client.post(
            "/api/me/wallet/withdrawals",
            headers=self.headers,
            json=self.withdrawal_payload(amount_cents=12345),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available_cents"], 0)
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, 0)

    def test_withdrawal_only_changes_the_authenticated_users_wallet(self):
        with self.Session() as db:
            other_user = User(
                email=f"{uuid4().hex}@example.com",
                hashed_password="x" * 60,
                wallet=Wallet(available_cents=9900),
            )
            db.add(other_user)
            db.commit()
            other_user_id = other_user.id

        response = self.client.post(
            "/api/me/wallet/withdrawals",
            headers=self.headers,
            json=self.withdrawal_payload(),
        )

        self.assertEqual(response.status_code, 200)
        with self.Session() as db:
            own_wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            other_wallet = db.scalar(
                select(Wallet).where(Wallet.user_id == other_user_id)
            )
            self.assertEqual(own_wallet.available_cents, 7345)
            self.assertEqual(other_wallet.available_cents, 9900)

    def test_concurrent_withdrawals_cannot_overdraw_the_wallet(self):
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            wallet.available_cents = 5000
            db.commit()

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def make_withdrawal():
            with self.Session() as db:
                barrier.wait()
                try:
                    withdraw_funds(db, user_id=self.user_id, amount_cents=4000)
                    db.commit()
                    outcome = "success"
                except InsufficientAvailableBalance:
                    db.rollback()
                    outcome = "insufficient"
                with outcomes_lock:
                    outcomes.append(outcome)

        threads = [threading.Thread(target=make_withdrawal) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(outcomes, ["success", "insufficient"])
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, 1000)


if __name__ == "__main__":
    unittest.main()
