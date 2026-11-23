"""Proves unitàries de validació sense dependències HTTP ni de base de dades."""
from datetime import UTC, datetime, timedelta
import unittest

from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.opportunity import OpportunityCreate
from app.schemas.promoting_entity import PromotingEntityCreate
from app.schemas.wallet import BalanceRead, MAX_SAFE_CENTS


class AuthSchemaTest(unittest.TestCase):
    def test_registration_normalizes_email_last_name_and_phone(self):
        request = RegisterRequest(
            email="Ada.Lovelace@Example.COM",
            first_name="Ada",
            last_name="   ",
            phone="+34 612 345 678",
            password="password1",
        )

        self.assertEqual(request.email, "ada.lovelace@example.com")
        self.assertIsNone(request.last_name)
        self.assertEqual(request.phone, "+34612345678")

    def test_registration_rejects_invalid_phone_and_password_length(self):
        valid_request = {
            "email": "ada@example.com",
            "first_name": "Ada",
            "phone": "+34612345678",
            "password": "password1",
        }
        invalid_requests = (
            {**valid_request, "phone": "not-a-phone"},
            {**valid_request, "password": "short"},
            {**valid_request, "password": "x" * 73},
        )

        for payload in invalid_requests:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    RegisterRequest(**payload)

    def test_login_normalizes_email_and_rejects_a_password_over_the_limit(self):
        request = LoginRequest(email="ADA@EXAMPLE.COM", password="password1")

        self.assertEqual(request.email, "ada@example.com")
        with self.assertRaises(ValidationError):
            LoginRequest(email="ada@example.com", password="x" * 73)


class FinancialSchemaTest(unittest.TestCase):
    def test_balance_requires_a_safe_non_negative_integer_amount(self):
        self.assertEqual(BalanceRead(available_cents=0, committed_cents=0).currency, "eur")

        for amount_cents in (-1, MAX_SAFE_CENTS + 1):
            with self.subTest(amount_cents=amount_cents):
                with self.assertRaises(ValidationError):
                    BalanceRead(available_cents=amount_cents, committed_cents=0)

    def test_opportunity_requires_positive_target_and_non_negative_committed_amount(self):
        valid_opportunity = {
            "type": "real_estate",
            "title": "Edificio en Girona",
            "description": "Rehabilitación residencial.",
            "location": "Girona",
            "target_amount_cents": 100_000,
            "deadline": datetime.now(UTC) + timedelta(days=30),
        }

        for changes in (
            {"target_amount_cents": 0},
            {"committed_cents": -1},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    OpportunityCreate(**{**valid_opportunity, **changes})


class PromotingEntitySchemaTest(unittest.TestCase):
    def test_promoting_entity_strips_optional_text_and_rejects_blank_legal_name(self):
        entity = PromotingEntityCreate(
            legal_name="  Promotora Ada SL  ", location="  Barcelona  "
        )

        self.assertEqual(entity.legal_name, "Promotora Ada SL")
        self.assertEqual(entity.location, "Barcelona")
        with self.assertRaises(ValidationError):
            PromotingEntityCreate(legal_name="   ")


if __name__ == "__main__":
    unittest.main()
