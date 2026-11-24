"""Webhook de Stripe amb la verificació de signatura real (US04.2).

Cap prova substitueix `stripe.Webhook.construct_event`: el cos es signa aquí amb el
secret de proves i la ruta el valida amb la llibreria de Stripe, sense xarxa.
"""
import json
import time
import unittest

from sqlalchemy import delete

from app.models.wallet import Wallet
from integration_support import (
    IntegrationTestCase,
    payment_event,
    signature_header,
)

INVALID_SIGNATURE = {"detail": "Invalid Stripe webhook signature"}
INVALID_PAYLOAD = {"detail": "Invalid Stripe webhook payload"}
INVALID_PAYMENT = {"detail": "Invalid Stripe payment data"}


class SignedStripeWebhookTest(IntegrationTestCase):
    database_prefix = "stripe_webhook_integration_test_"

    def setUp(self):
        super().setUp()
        self.user = self.new_actor()

    def assert_nothing_credited(self):
        self.assertEqual(self.balances(self.user.id), (0, 0))
        self.assertEqual(self.deposits(self.user.id), [])

    def test_event_with_a_valid_signature_credits_the_wallet(self):
        event = payment_event(self.user.id, 5_000)

        response = self.post_event(event)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})
        (deposit,) = self.deposits(self.user.id)
        self.assertEqual(deposit.stripe_event_id, event["id"])
        self.assertEqual(deposit.stripe_payment_intent_id, event["data"]["object"]["id"])
        self.assertEqual((deposit.amount_cents, deposit.currency), (5_000, "eur"))
        self.assertEqual(self.balances(self.user.id), (5_000, 0))
        # El saldo acreditat és el que l'usuari veu a la seva cartera.
        wallet = self.user.client.get("/api/me/wallet")
        self.assertEqual(
            wallet.json(), {"available_cents": 5_000, "committed_cents": 0, "currency": "eur"}
        )

    def test_missing_wrong_or_stale_signature_is_rejected_without_crediting(self):
        payload = json.dumps(payment_event(self.user.id, 5_000)).encode()
        tampered = json.dumps(payment_event(self.user.id, 500_000)).encode()
        now = int(time.time())
        cases = {
            "signature of another secret": (
                payload,
                signature_header(payload, secret="whsec_of_someone_else"),
            ),
            "made-up signature": (payload, f"t={now},v1={'0' * 64}"),
            "body changed after signing": (tampered, signature_header(payload)),
            # Stripe tolera 300 segons: un esdeveniment antic podria ser una repetició.
            "stale timestamp": (payload, signature_header(payload, timestamp=now - 301)),
            "header without timestamp": (payload, signature_header(payload).split(",")[1]),
            "header that is not a signature": (payload, "test_signature"),
        }

        for name, (body, signature) in cases.items():
            with self.subTest(name):
                response = self.post_event(body, signature=signature)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), INVALID_SIGNATURE)
                self.assert_nothing_credited()

        with self.subTest("no signature header"):
            response = self.anonymous.post(
                "/api/webhooks/stripe",
                content=payload,
                headers={"content-type": "application/json"},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), INVALID_SIGNATURE)
            self.assert_nothing_credited()

        # El mateix cos amb la signatura correcta sí que s'acredita: només fallava la signatura.
        self.assertEqual(self.post_event(payload).json(), {"status": "success"})
        self.assertEqual(self.balances(self.user.id), (5_000, 0))

    def test_signed_payload_that_is_not_json_is_rejected(self):
        response = self.post_event(b"not-json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), INVALID_PAYLOAD)
        self.assert_nothing_credited()

    def test_invalid_payment_data_is_rejected_without_crediting(self):
        user_id = self.user.id
        without_event_id = payment_event(user_id, 5_000)
        del without_event_id["id"]
        without_amounts = payment_event(user_id, 5_000)
        del without_amounts["data"]["object"]["amount"]
        del without_amounts["data"]["object"]["amount_received"]
        cases = {
            "no metadata": payment_event(user_id, 5_000, metadata=None),
            "metadata without user": payment_event(user_id, 5_000, metadata={}),
            "user id that is not a number": payment_event(
                user_id, 5_000, metadata={"user_id": "abc"}
            ),
            "amount below the minimum deposit": payment_event(user_id, 49),
            "amount that is not a number": payment_event(
                user_id, 5_000, amount_received="abc"
            ),
            "no amount": without_amounts,
            "currency other than euro": payment_event(user_id, 5_000, currency="usd"),
            "no currency": payment_event(user_id, 5_000, currency=None),
            "event without id": without_event_id,
            "payment intent without id": payment_event(user_id, 5_000, id=None),
        }

        for name, event in cases.items():
            with self.subTest(name):
                response = self.post_event(event)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), INVALID_PAYMENT)
                self.assert_nothing_credited()

    def test_other_signed_events_are_acknowledged_without_crediting(self):
        # Un pagament fallit porta les mateixes dades que un de confirmat, però no acredita.
        event = payment_event(self.user.id, 5_000)
        event["type"] = "payment_intent.payment_failed"

        response = self.post_event(event)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ignored"})
        self.assert_nothing_credited()

    def test_redelivered_payment_is_acknowledged_without_crediting_again(self):
        event = payment_event(self.user.id, 5_000)
        # Stripe pot tornar a avisar del mateix pagament amb un altre esdeveniment.
        same_payment = payment_event(
            self.user.id, 5_000, id=event["data"]["object"]["id"]
        )

        first = self.post_event(event)
        same_event = self.post_event(event)
        other_event = self.post_event(same_payment)

        self.assertEqual((first.status_code, first.json()), (200, {"status": "success"}))
        for repeated in (same_event, other_event):
            # 200 perquè Stripe deixi de reintentar; el saldo no es torna a sumar.
            self.assertEqual(repeated.status_code, 200)
            self.assertEqual(repeated.json(), {"status": "already_processed"})
        self.assertEqual(self.balances(self.user.id), (5_000, 0))
        self.assertEqual(
            [deposit.stripe_event_id for deposit in self.deposits(self.user.id)],
            [event["id"]],
        )

    def test_duplicate_deliveries_arriving_at_once_credit_once(self):
        payload = json.dumps(payment_event(self.user.id, 5_000)).encode()

        responses = self.simultaneous(
            [lambda client: self.post_event(payload, client=client)] * 4,
            queued_behind_wallet_of=self.user.id,
        )

        self.assertEqual([response.status_code for response in responses], [200] * 4)
        statuses = sorted(response.json()["status"] for response in responses)
        self.assertEqual(statuses, ["already_processed"] * 3 + ["success"])
        self.assertEqual(self.balances(self.user.id), (5_000, 0))
        self.assertEqual(len(self.deposits(self.user.id)), 1)

    def test_amount_falls_back_to_amount_when_amount_received_is_absent(self):
        event = payment_event(self.user.id, 5_000)
        del event["data"]["object"]["amount_received"]

        response = self.post_event(event)

        self.assertEqual((response.status_code, response.json()), (200, {"status": "success"}))
        self.assertEqual(self.balances(self.user.id), (5_000, 0))

    def test_deposit_creates_the_wallet_when_the_user_has_none(self):
        # Usuaris anteriors a la cartera podrien no tenir-ne: l'ingrés no es pot perdre.
        with self.Session() as db:
            db.execute(delete(Wallet).where(Wallet.user_id == self.user.id))
            db.commit()
        self.assertIsNone(self.balances(self.user.id))

        response = self.post_event(payment_event(self.user.id, 5_000))

        self.assertEqual((response.status_code, response.json()), (200, {"status": "success"}))
        self.assertEqual(self.balances(self.user.id), (5_000, 0))

    def test_deposits_of_two_users_do_not_mix(self):
        other = self.new_actor()

        self.deposit(self.user.id, 5_000)
        self.deposit(other.id, 7_000)

        self.assertEqual(self.balances(self.user.id), (5_000, 0))
        self.assertEqual(self.balances(other.id), (7_000, 0))
        self.assertEqual(
            other.client.get("/api/me/wallet").json()["available_cents"], 7_000
        )
        self.assertEqual(len(self.deposits(self.user.id)), 1)
        self.assertEqual(len(self.deposits(other.id)), 1)


if __name__ == "__main__":
    unittest.main()
