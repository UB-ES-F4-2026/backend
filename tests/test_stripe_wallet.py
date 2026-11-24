"""Endpoints d'ingrés Stripe contra una base PostgreSQL aïllada i migrada."""
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import stripe
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.security import SESSION_COOKIE, generate_session_token, hash_session_token
from app.database import engine
from app.main import app
from app.models.session import UserSession
from app.models.user import User
from app.models.wallet import Wallet
from app.models.wallet_deposit import WalletDeposit


class StripeWalletTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "stripe_wallet_test_" + uuid4().hex
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
        # Identificadors de Stripe propis de cada prova: són únics a la base de dades.
        self.event_id = f"evt_{uuid4().hex}"
        self.payment_intent_id = f"pi_{uuid4().hex}"
        with self.Session() as db:
            user = User(
                email=f"{uuid4().hex}@example.com",
                hashed_password="x" * 60,
                wallet=Wallet(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            token = generate_session_token()
            db.add(UserSession(token=hash_session_token(token), user_id=user.id))
            db.commit()
            self.user_id = user.id
            self.cookie = f"{SESSION_COOKIE}={token}"

    @patch("app.api.routes.wallet.stripe.PaymentIntent.create")
    def test_create_deposit_intent_for_authenticated_user(self, mock_create):
        intent = MagicMock(client_secret="pi_secret", id="pi_test_123")
        mock_create.return_value = intent

        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test"}):
            response = self.client.post(
                "/api/me/wallet/deposit-intent",
                json={"amount_cents": 5000},
                headers={"Cookie": self.cookie},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"client_secret": "pi_secret", "payment_intent_id": "pi_test_123"},
        )
        mock_create.assert_called_once_with(
            amount=5000,
            currency="eur",
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata={"user_id": str(self.user_id)},
        )

    @patch("app.api.routes.wallet.stripe.PaymentIntent.create")
    def test_deposit_intent_validates_authentication_and_integer_cents(self, mock_create):
        unauthenticated = self.client.post(
            "/api/me/wallet/deposit-intent", json={"amount_cents": 5000}
        )
        below_minimum = self.client.post(
            "/api/me/wallet/deposit-intent",
            json={"amount_cents": 49},
            headers={"Cookie": self.cookie},
        )
        fractional = self.client.post(
            "/api/me/wallet/deposit-intent",
            json={"amount_cents": 50.0},
            headers={"Cookie": self.cookie},
        )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(below_minimum.status_code, 422)
        self.assertEqual(fractional.status_code, 422)
        mock_create.assert_not_called()

    def test_deposit_endpoints_require_stripe_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            intent_response = self.client.post(
                "/api/me/wallet/deposit-intent",
                json={"amount_cents": 5000},
                headers={"Cookie": self.cookie},
            )
            webhook_response = self.post_webhook()

        self.assertEqual(intent_response.status_code, 503)
        self.assertEqual(webhook_response.status_code, 503)

    @patch("app.api.routes.wallet.stripe.PaymentIntent.create")
    def test_stripe_error_does_not_create_a_deposit(self, mock_create):
        mock_create.side_effect = stripe.error.CardError(
            "Card declined", param="payment_method", code="card_declined"
        )

        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test"}):
            response = self.client.post(
                "/api/me/wallet/deposit-intent",
                json={"amount_cents": 5000},
                headers={"Cookie": self.cookie},
            )

        self.assertEqual(response.status_code, 400)
        self.assert_wallet_state(available_cents=0, deposit_count=0)

    @patch("app.api.routes.webhooks.stripe.Webhook.construct_event")
    def test_successful_webhook_credits_wallet_once(self, mock_construct_event):
        mock_construct_event.return_value = self.payment_event()

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test"}):
            first = self.post_webhook()
            second = self.post_webhook()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {"status": "success"})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), {"status": "already_processed"})
        self.assert_wallet_state(available_cents=5000, deposit_count=1)

    @patch("app.api.routes.webhooks.stripe.Webhook.construct_event")
    def test_unsuccessful_payment_webhook_does_not_change_wallet(self, mock_construct_event):
        mock_construct_event.return_value = {
            "id": "evt_failed",
            "type": "payment_intent.payment_failed",
            "data": {"object": {}},
        }

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test"}):
            response = self.post_webhook()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ignored"})
        self.assert_wallet_state(available_cents=0, deposit_count=0)

    @patch("app.api.routes.webhooks.stripe.Webhook.construct_event")
    def test_invalid_webhook_signature_does_not_change_wallet(self, mock_construct_event):
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", sig_header="invalid"
        )

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test"}):
            response = self.post_webhook()

        self.assertEqual(response.status_code, 400)
        self.assert_wallet_state(available_cents=0, deposit_count=0)

    def payment_event(self) -> dict:
        return {
            "id": self.event_id,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": self.payment_intent_id,
                    "amount_received": 5000,
                    "currency": "eur",
                    "metadata": {"user_id": str(self.user_id)},
                }
            },
        }

    def post_webhook(self):
        return self.client.post(
            "/api/webhooks/stripe",
            content=b'{"type":"payment_intent.succeeded"}',
            headers={"stripe-signature": "test_signature"},
        )

    def assert_wallet_state(self, *, available_cents: int, deposit_count: int):
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id))
            self.assertEqual(wallet.available_cents, available_cents)
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(WalletDeposit)
                    .where(WalletDeposit.user_id == self.user_id)
                ),
                deposit_count,
            )


if __name__ == "__main__":
    unittest.main()
