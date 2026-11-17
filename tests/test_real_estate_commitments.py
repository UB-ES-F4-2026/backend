"""Comprometre una aportació immobiliària (US03.1.1) a través de l'API."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.security import SESSION_COOKIE, generate_session_token, hash_session_token
from app.database import engine, get_db
from app.main import app
from app.models.commitment import Commitment
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.real_estate_opportunity import (
    AssetType,
    IntendedUse,
    RealEstateOpportunity,
    RealEstatePurpose,
)
from app.models.session import UserSession
from app.models.user import User
from app.models.wallet import Wallet

NOT_AVAILABLE = "Opportunity not available"
BELOW_MINIMUM = "Amount below the minimum contribution"
INSUFFICIENT_FUNDS = "Insufficient funds"
NOT_ACCEPTED = "Opportunity no longer accepts this contribution"
# Marge perquè un fil acabi; si se supera, el test falla en lloc de penjar-se.
THREAD_TIMEOUT = 30


class RealEstateCommitmentsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "real_estate_commitments_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        # Les proves de concurrència obren una connexió per petició simultània.
        cls.isolated = create_engine(
            engine.url.set(database=cls.database), pool_size=10, max_overflow=10
        )
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        cls.Session = sessionmaker(bind=cls.isolated, autoflush=False, expire_on_commit=False)

        def override_get_db():
            with cls.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app, base_url="https://testserver")

        with cls.Session() as db:
            promoter = User(
                email="promoter@example.com",
                hashed_password="x" * 60,
                wallet=Wallet(available_cents=1_000_00),
            )
            db.add(promoter)
            db.flush()
            db.add(PromotingEntity(user_id=promoter.id, legal_name="Promociones Girona SL"))
            token = generate_session_token()
            db.add(UserSession(token=hash_session_token(token), user_id=promoter.id))
            db.commit()
            cls.promoter_id = promoter.id
            cls.promoter_cookie = f"{SESSION_COOKIE}={token}"

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def create_user(self, available_cents: int) -> tuple[int, str]:
        """Crea un usuari amb saldo i sessió iniciada; retorna el seu id i la cookie."""
        with self.Session() as db:
            user = User(
                email=f"{uuid4().hex}@example.com",
                hashed_password="x" * 60,
                wallet=Wallet(available_cents=available_cents),
            )
            db.add(user)
            db.flush()
            token = generate_session_token()
            db.add(UserSession(token=hash_session_token(token), user_id=user.id))
            db.commit()
            return user.id, f"{SESSION_COOKIE}={token}"

    def create_opportunity(self, real_estate=True, **changes) -> int:
        values = {
            "user_id": self.promoter_id,
            "type": OpportunityType.REAL_ESTATE,
            "status": OpportunityStatus.PUBLISHED,
            "title": "Rehabilitació d'un edifici",
            "description": "Descripció.",
            "location": "Girona",
            "target_amount_cents": 72_000_00,
            "committed_cents": 45_000_00,
            "minimum_contribution_cents": 50_00,
            "deadline": datetime.now(UTC) + timedelta(days=30),
            "date_published": datetime.now(UTC),
        }
        values.update(changes)
        opportunity = Opportunity(**values)
        if real_estate:
            opportunity.real_estate = RealEstateOpportunity(
                purpose=RealEstatePurpose.ACQUISITION_AND_RENOVATION,
                intended_use=IntendedUse.RENTAL,
                asset_type=AssetType.RESIDENTIAL,
                surface_m2=Decimal("950.50"),
                planned_housing_units=12,
                estimated_works_end=date(2027, 6, 30),
                estimated_rental_start=date(2027, 9, 1),
            )
        with self.Session() as db:
            db.add(opportunity)
            db.commit()
            return opportunity.id

    def commit(self, opportunity_id: int, cookie: str | None, body, client=None):
        headers = {"Cookie": cookie} if cookie else {}
        return (client or self.client).post(
            f"/api/opportunities/{opportunity_id}/commitments", json=body, headers=headers
        )

    def balances(self, user_id: int) -> tuple[int, int]:
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
            return wallet.available_cents, wallet.committed_cents

    def opportunity_committed(self, opportunity_id: int) -> int:
        with self.Session() as db:
            return db.get(Opportunity, opportunity_id).committed_cents

    def commitments(self, **filters) -> list[Commitment]:
        with self.Session() as db:
            return list(
                db.scalars(select(Commitment).filter_by(**filters).order_by(Commitment.id))
            )

    def assert_nothing_changed(self, user_id, opportunity_id, available_cents, committed_cents):
        self.assertEqual(self.balances(user_id), (available_cents, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), committed_cents)
        self.assertEqual(self.commitments(opportunity_id=opportunity_id), [])


class CommitContributionTest(RealEstateCommitmentsTestCase):
    def test_commits_the_contribution_and_returns_the_updated_figures(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        response = self.commit(opportunity_id, cookie, {"amount_cents": 100_00})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers["cache-control"], "no-store")
        body = response.json()
        self.assertEqual(set(body), {"commitment", "opportunity", "wallet"})
        (stored,) = self.commitments(opportunity_id=opportunity_id)
        self.assertEqual(stored.user_id, user_id)
        self.assertEqual(
            body["commitment"],
            {
                "id": stored.id,
                "opportunity_id": opportunity_id,
                "amount_cents": 100_00,
                "created_at": body["commitment"]["created_at"],
            },
        )
        self.assertEqual(datetime.fromisoformat(body["commitment"]["created_at"]), stored.created_at)
        self.assertEqual(
            body["opportunity"],
            {"id": opportunity_id, "target_amount_cents": 72_000_00, "committed_cents": 45_100_00},
        )
        self.assertEqual(
            body["wallet"],
            {"available_cents": 150_00, "committed_cents": 100_00, "currency": "eur"},
        )

        # El detall i «Mi saldo» mostren el mateix que la resposta.
        detail = self.client.get(f"/api/opportunities/{opportunity_id}").json()
        self.assertEqual(detail["committed_cents"], 45_100_00)
        wallet = self.client.get("/api/me/wallet", headers={"Cookie": cookie}).json()
        self.assertEqual(wallet, body["wallet"])

    def test_reaching_the_target_removes_the_opportunity_from_the_catalog(self):
        user_id, cookie = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity(committed_cents=71_500_00)
        catalog = self.client.get("/api/opportunities").json()
        self.assertIn(opportunity_id, [item["id"] for item in catalog])

        response = self.commit(opportunity_id, cookie, {"amount_cents": 500_00})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["opportunity"]["committed_cents"], 72_000_00)
        catalog = self.client.get("/api/opportunities").json()
        self.assertNotIn(opportunity_id, [item["id"] for item in catalog])
        # El detall segueix sent públic, amb l'objectiu assolit.
        detail = self.client.get(f"/api/opportunities/{opportunity_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["committed_cents"], detail.json()["target_amount_cents"])

        # Un cop finançada ja no admet cap més aportació.
        again = self.commit(opportunity_id, cookie, {"amount_cents": 50_00})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"], NOT_ACCEPTED)
        self.assertEqual(self.balances(user_id), (500_00, 500_00))

    def test_same_user_can_contribute_several_times(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        first = self.commit(opportunity_id, cookie, {"amount_cents": 100_00})
        second = self.commit(opportunity_id, cookie, {"amount_cents": 50_00})

        self.assertEqual((first.status_code, second.status_code), (201, 201))
        stored = self.commitments(opportunity_id=opportunity_id)
        self.assertEqual([c.amount_cents for c in stored], [100_00, 50_00])
        self.assertEqual(self.balances(user_id), (100_00, 150_00))

    def test_promoter_can_contribute_to_their_own_opportunity(self):
        opportunity_id = self.create_opportunity()
        available_cents, committed_cents = self.balances(self.promoter_id)

        response = self.commit(opportunity_id, self.promoter_cookie, {"amount_cents": 100_00})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.balances(self.promoter_id),
            (available_cents - 100_00, committed_cents + 100_00),
        )

    def test_opportunity_without_minimum_accepts_any_positive_amount(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity(minimum_contribution_cents=None)

        response = self.commit(opportunity_id, cookie, {"amount_cents": 1})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.balances(user_id), (249_99, 1))

    def test_amount_equal_to_the_minimum_is_accepted(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity(minimum_contribution_cents=50_00)

        response = self.commit(opportunity_id, cookie, {"amount_cents": 50_00})

        self.assertEqual(response.status_code, 201)


class CommitContributionRejectionTest(RealEstateCommitmentsTestCase):
    def test_requires_an_active_session(self):
        user_id, _ = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        for cookie in (None, f"{SESSION_COOKIE}=not-a-session"):
            with self.subTest(cookie=cookie):
                response = self.commit(opportunity_id, cookie, {"amount_cents": 100_00})
                self.assertEqual(response.status_code, 401)

        self.assert_nothing_changed(user_id, opportunity_id, 250_00, 45_000_00)

    def test_amount_below_the_minimum_is_rejected(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity(minimum_contribution_cents=50_00)

        response = self.commit(opportunity_id, cookie, {"amount_cents": 49_99})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], BELOW_MINIMUM)
        self.assert_nothing_changed(user_id, opportunity_id, 250_00, 45_000_00)

    def test_amount_must_be_a_positive_whole_number_of_cents(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        bodies = (
            {},
            {"amount_cents": None},
            {"amount_cents": 0},
            {"amount_cents": -100_00},
            # Més de dos decimals en euros: fraccions de cèntim.
            {"amount_cents": 100_00.5},
            {"amount_cents": "10000"},
            {"amount_cents": 2**53},
        )
        for body in bodies:
            with self.subTest(body=body):
                response = self.commit(opportunity_id, cookie, body)
                self.assertEqual(response.status_code, 422)

        self.assert_nothing_changed(user_id, opportunity_id, 250_00, 45_000_00)

    def test_amount_above_the_available_balance_is_rejected(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        response = self.commit(opportunity_id, cookie, {"amount_cents": 300_00})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], INSUFFICIENT_FUNDS)
        self.assert_nothing_changed(user_id, opportunity_id, 250_00, 45_000_00)

    def test_amount_above_the_remaining_capital_is_rejected(self):
        user_id, cookie = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity(committed_cents=71_500_00)

        response = self.commit(opportunity_id, cookie, {"amount_cents": 500_01})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], NOT_ACCEPTED)
        self.assert_nothing_changed(user_id, opportunity_id, 1_000_00, 71_500_00)

    def test_opportunities_out_of_funding_no_longer_accept_contributions(self):
        user_id, cookie = self.create_user(250_00)
        out_of_funding = {
            "deadline passed": {"deadline": datetime.now(UTC) - timedelta(minutes=1)},
            "closed early": {
                "status": OpportunityStatus.CLOSED,
                "date_closed": datetime.now(UTC),
            },
            "target reached": {"committed_cents": 72_000_00},
        }
        for reason, changes in out_of_funding.items():
            with self.subTest(reason=reason):
                opportunity_id = self.create_opportunity(**changes)
                committed_cents = self.opportunity_committed(opportunity_id)

                response = self.commit(opportunity_id, cookie, {"amount_cents": 100_00})

                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"], NOT_ACCEPTED)
                self.assert_nothing_changed(user_id, opportunity_id, 250_00, committed_cents)

    def test_opportunities_that_are_not_public_real_estate_are_not_found(self):
        user_id, cookie = self.create_user(250_00)
        hidden = {
            "draft": {"status": OpportunityStatus.DRAFT, "date_published": None},
            "rejected": {"status": OpportunityStatus.REJECTED, "date_published": None},
            "equity": {"type": OpportunityType.EQUITY, "real_estate": False},
        }
        for reason, changes in hidden.items():
            with self.subTest(reason=reason):
                opportunity_id = self.create_opportunity(**changes)

                response = self.commit(opportunity_id, cookie, {"amount_cents": 100_00})

                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["detail"], NOT_AVAILABLE)
                self.assert_nothing_changed(user_id, opportunity_id, 250_00, 45_000_00)

        unknown = self.commit(999_999_999, cookie, {"amount_cents": 100_00})
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json()["detail"], NOT_AVAILABLE)
        self.assertEqual(self.balances(user_id), (250_00, 0))

    def test_a_rejected_contribution_does_not_block_the_next_one(self):
        user_id, cookie = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        rejected = self.commit(opportunity_id, cookie, {"amount_cents": 300_00})
        accepted = self.commit(opportunity_id, cookie, {"amount_cents": 100_00})

        self.assertEqual((rejected.status_code, accepted.status_code), (409, 201))
        self.assertEqual(self.balances(user_id), (150_00, 100_00))


class CommitContributionConcurrencyTest(RealEstateCommitmentsTestCase):
    def simultaneous(self, requests: list[tuple[int, str, int]]) -> list:
        """Envia totes les peticions alhora, cadascuna amb el seu client."""
        barrier = threading.Barrier(len(requests))

        def send(opportunity_id: int, cookie: str, amount_cents: int):
            client = TestClient(app, base_url="https://testserver")
            barrier.wait(timeout=THREAD_TIMEOUT)
            return self.commit(
                opportunity_id, cookie, {"amount_cents": amount_cents}, client=client
            )

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [pool.submit(send, *request) for request in requests]
            return [future.result(timeout=THREAD_TIMEOUT) for future in futures]

    def test_contributions_competing_for_the_remaining_capital(self):
        opportunity_id = self.create_opportunity(committed_cents=71_500_00)
        users = [self.create_user(1_000_00) for _ in range(8)]

        responses = self.simultaneous(
            [(opportunity_id, cookie, 300_00) for _, cookie in users]
        )

        # Falten 500,00 €: només hi cap una aportació de 300,00 €.
        codes = [response.status_code for response in responses]
        self.assertEqual(codes.count(201), 1)
        self.assertEqual(codes.count(409), 7)
        self.assertEqual(self.opportunity_committed(opportunity_id), 71_800_00)
        stored = self.commitments(opportunity_id=opportunity_id)
        self.assertEqual([c.amount_cents for c in stored], [300_00])
        for (user_id, _), response in zip(users, responses):
            if response.status_code == 201:
                self.assertEqual(self.balances(user_id), (700_00, 300_00))
            else:
                self.assertEqual(response.json()["detail"], NOT_ACCEPTED)
                self.assertEqual(self.balances(user_id), (1_000_00, 0))

    def test_contributions_competing_to_complete_the_target(self):
        opportunity_id = self.create_opportunity(committed_cents=71_500_00)
        users = [self.create_user(1_000_00) for _ in range(8)]

        responses = self.simultaneous(
            [(opportunity_id, cookie, 500_00) for _, cookie in users]
        )

        codes = [response.status_code for response in responses]
        self.assertEqual(codes.count(201), 1)
        self.assertEqual(codes.count(409), 7)
        self.assertEqual(self.opportunity_committed(opportunity_id), 72_000_00)
        catalog = self.client.get("/api/opportunities").json()
        self.assertNotIn(opportunity_id, [item["id"] for item in catalog])

    def test_contributions_of_one_user_competing_for_the_same_balance(self):
        user_id, cookie = self.create_user(100_00)
        opportunities = [self.create_opportunity() for _ in range(8)]

        responses = self.simultaneous(
            [(opportunity_id, cookie, 50_00) for opportunity_id in opportunities]
        )

        # Amb 100,00 € només hi caben dues aportacions de 50,00 €.
        codes = [response.status_code for response in responses]
        self.assertEqual(codes.count(201), 2)
        self.assertEqual(codes.count(409), 6)
        self.assertEqual(self.balances(user_id), (0, 100_00))
        for opportunity_id, response in zip(opportunities, responses):
            if response.status_code == 201:
                self.assertEqual(self.opportunity_committed(opportunity_id), 45_050_00)
            else:
                self.assertEqual(response.json()["detail"], INSUFFICIENT_FUNDS)
                self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)


if __name__ == "__main__":
    unittest.main()
