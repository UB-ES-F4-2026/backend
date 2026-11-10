"""Unit tests for Stripe payment intents and webhook handling."""
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import stripe
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database import engine, get_db
from app.main import app
from app.models.user import User
from app.models.wallet import Wallet


class StripeWalletTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Crea una base de datos aislada para ejecutar las pruebas con migraciones aplicadas."""
        cls.database = "stripe_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
            
        cls.isolated = create_engine(engine.url.set(database=cls.database))
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        Session = sessionmaker(bind=cls.isolated, autoflush=False, expire_on_commit=False)

        def override_get_db():
            with Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.Session = Session

    @classmethod
    def tearDownClass(cls):
        """Elimina la base de datos temporal al finalizar la suite."""
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def setUp(self):
        """Inserta un usuario verificado y su billetera inicial a 0€ para cada test."""
        with self.Session() as db:
            user = User(
                email=f"user_{uuid4().hex[:8]}@example.com", 
                hashed_password="hashed_password_sample"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            wallet = Wallet(user_id=user.id, available_cents=0)
            db.add(wallet)
            db.commit()

            self.test_user_id = user.id
            self.test_user_email = user.email

    def test_get_wallet_balance_returns_authenticated_users_persisted_balance(self):
        with self.Session() as db:
            user = db.get(User, self.test_user_id)
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.test_user_id))
            wallet.available_cents = 12345
            db.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            response = self.client.get("/api/me/wallet")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"available_cents": 12345, "currency": "eur"}
        )

    @patch("stripe.PaymentIntent.create")
    def test_create_deposit_intent_success(self, mock_stripe_create):
        """Verifica que un usuario autenticado puede solicitar la creación de un PaymentIntent."""
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_abc123"
        mock_intent.id = "pi_test_12345"
        mock_stripe_create.return_value = mock_intent

        with self.Session() as db:
            user = db.get(User, self.test_user_id)
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            with patch("app.api.routes.wallet.stripe.api_key", "sk_test_dummy"):
                response = self.client.post(
                    "/api/me/wallet/deposit-intent",
                    json={"amount_cents": 5000}
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["client_secret"], "pi_test_secret_abc123")
        self.assertEqual(data["payment_intent_id"], "pi_test_12345")
        
        # Validar que los parámetros enviados a la SDK de Stripe son correctos
        mock_stripe_create.assert_called_once_with(
            amount=5000,
            currency="eur",
            metadata={"user_id": str(self.test_user_id)}
        )

    @patch("stripe.Webhook.construct_event")
    def test_stripe_webhook_payment_succeeded_updates_wallet(self, mock_construct_event):
        """Verifica que el evento payment_intent.succeeded incrementa el saldo en la base de datos."""
        mock_construct_event.return_value = stripe.StripeObject.construct_from(
            {
                "id": "evt_test_12345",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_test_12345",
                        "amount": 5000,
                        "currency": "eur",
                        "metadata": {"user_id": str(self.test_user_id)},
                    }
                },
            },
            None,
        )

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret_key"}):
            response = self.client.post(
                "/api/webhooks/stripe",
                content=b'{"type": "payment_intent.succeeded"}',
                headers={"stripe-signature": "t=123,v1=test_signature"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})

        # Confirmar persistencia en PostgreSQL
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.test_user_id))
            self.assertIsNotNone(wallet)
            self.assertEqual(wallet.available_cents, 5000)

    @patch("stripe.Webhook.construct_event")
    def test_stripe_webhook_creates_missing_wallet_before_crediting(self, mock_construct_event):
        mock_construct_event.return_value = stripe.StripeObject.construct_from(
            {
                "id": "evt_test_legacy_wallet",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_test_legacy_wallet",
                        "amount": 5000,
                        "currency": "eur",
                        "metadata": {"user_id": str(self.test_user_id)},
                    }
                },
            },
            None,
        )
        with self.Session() as db:
            db.delete(db.scalar(select(Wallet).where(Wallet.user_id == self.test_user_id)))
            db.commit()

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret_key"}):
            response = self.client.post(
                "/api/webhooks/stripe",
                content=b'{"type": "payment_intent.succeeded"}',
                headers={"stripe-signature": "t=123,v1=test_signature"},
            )

        self.assertEqual(response.status_code, 200)
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.test_user_id))
            self.assertIsNotNone(wallet)
            self.assertEqual(wallet.available_cents, 5000)

    @patch("stripe.Webhook.construct_event")
    def test_duplicate_stripe_webhook_does_not_credit_wallet_twice(self, mock_construct_event):
        mock_construct_event.return_value = {
            "id": "evt_test_duplicate",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_duplicate",
                    "amount": 5000,
                    "currency": "eur",
                    "metadata": {"user_id": str(self.test_user_id)},
                }
            },
        }

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret_key"}):
            for _ in range(2):
                response = self.client.post(
                    "/api/webhooks/stripe",
                    content=b'{"type": "payment_intent.succeeded"}',
                    headers={"stripe-signature": "t=123,v1=test_signature"},
                )
                self.assertEqual(response.status_code, 200)

        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.test_user_id))
            self.assertEqual(wallet.available_cents, 5000)

    @patch("stripe.Webhook.construct_event")
    def test_stripe_webhook_invalid_signature_returns_400(self, mock_construct_event):
        """Verifica que peticiones con firma de webhook alterada son rechazadas con HTTP 400."""
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Firma no válida", sig_header="invalid_sig"
        )

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret_key"}):
            response = self.client.post(
                "/api/webhooks/stripe",
                content=b'{}',
                headers={"stripe-signature": "invalid_sig"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Firma del webhook de Stripe no válida", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()