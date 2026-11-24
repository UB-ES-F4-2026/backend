"""Consultar les inversions de l'usuari autenticat (US05.1)."""
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.commitments import reserve_funds
from app.core.security import SESSION_COOKIE, generate_session_token, hash_session_token
from app.database import engine, get_db
from app.main import app
from app.models.business_opportunity import (
    BusinessOpportunity,
    BusinessPhase,
    BusinessSector,
)
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

URL = "/api/me/commitments"
EMPTY_SUMMARY = {"total_committed_cents": 0, "commitments_count": 0, "in_funding_count": 0}


class UserCommitmentsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "user_commitments_test_" + uuid4().hex
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
        cls.client = TestClient(app, base_url="https://testserver")
        cls.promoter_id, cls.promoter_cookie = cls.create_user(10_000_00, promoter=True)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    @classmethod
    def create_user(cls, available_cents: int, promoter: bool = False) -> tuple[int, str]:
        """Crea un usuari amb saldo i sessió iniciada; retorna el seu id i la cookie."""
        with cls.Session() as db:
            user = User(
                email=f"{uuid4().hex}@example.com",
                hashed_password="x" * 60,
                wallet=Wallet(available_cents=available_cents),
            )
            db.add(user)
            db.flush()
            if promoter:
                db.add(PromotingEntity(user_id=user.id, legal_name="Promociones Ejemplo SL"))
            token = generate_session_token()
            db.add(UserSession(token=hash_session_token(token), user_id=user.id))
            db.commit()
            return user.id, f"{SESSION_COOKIE}={token}"

    def create_opportunity(
        self, opportunity_type=OpportunityType.REAL_ESTATE, specific_data=True, **changes
    ) -> int:
        values = {
            "user_id": self.promoter_id,
            "type": opportunity_type,
            "status": OpportunityStatus.PUBLISHED,
            "title": "Piso en Girona",
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
        if specific_data and opportunity_type == OpportunityType.EQUITY:
            opportunity.business = BusinessOpportunity(
                sector=BusinessSector.TECHNOLOGY,
                phase=BusinessPhase.GROWTH,
                pre_investment_valuation_cents=2_700_000_00,
            )
        elif specific_data:
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

    def commit(self, opportunity_id: int, cookie: str, amount_cents: int) -> dict:
        """Compromet l'import per l'API, com fa l'usuari; retorna el compromís creat."""
        response = self.client.post(
            f"/api/opportunities/{opportunity_id}/commitments",
            json={"amount_cents": amount_cents},
            headers={"Cookie": cookie},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["commitment"]

    def reserve(self, opportunity_id: int, user_id: int, amount_cents: int) -> int:
        """Reserva sense passar per l'API: l'aportació inicial d'una oportunitat no publicada."""
        with self.Session() as db:
            commitment = reserve_funds(
                db, user_id=user_id, opportunity_id=opportunity_id, amount_cents=amount_cents
            )
            db.commit()
            return commitment.id

    def set_created_at(self, commitment_id: int, created_at: datetime) -> None:
        with self.Session() as db:
            db.get(Commitment, commitment_id).created_at = created_at
            db.commit()

    def update_opportunity(self, opportunity_id: int, **changes) -> None:
        with self.Session() as db:
            opportunity = db.get(Opportunity, opportunity_id)
            for name, value in changes.items():
                setattr(opportunity, name, value)
            db.commit()

    def get(self, cookie: str | None):
        return self.client.get(URL, headers={"Cookie": cookie} if cookie else {})

    def get_ok(self, cookie: str) -> dict:
        response = self.get(cookie)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class AuthorizationTest(UserCommitmentsTestCase):
    def test_requires_a_session(self):
        response = self.get(None)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid or missing session"})

    def test_returns_only_the_commitments_of_the_authenticated_user(self):
        user_id, cookie = self.create_user(500_00)
        _, other_cookie = self.create_user(500_00)
        opportunity_id = self.create_opportunity()
        own = self.commit(opportunity_id, cookie, 100_00)
        foreign = self.commit(opportunity_id, other_cookie, 200_00)

        body = self.get_ok(cookie)
        other_body = self.get_ok(other_cookie)

        self.assertEqual([item["id"] for item in body["commitments"]], [own["id"]])
        self.assertEqual(body["summary"]["total_committed_cents"], 100_00)
        self.assertEqual([item["id"] for item in other_body["commitments"]], [foreign["id"]])
        self.assertEqual(other_body["summary"]["total_committed_cents"], 200_00)

    def test_does_not_expose_who_invested(self):
        _, cookie = self.create_user(500_00)
        self.commit(self.create_opportunity(), cookie, 100_00)

        (item,) = self.get_ok(cookie)["commitments"]

        self.assertEqual(
            set(item), {"id", "amount_cents", "created_at", "estimated_equity", "opportunity"}
        )
        self.assertEqual(
            set(item["opportunity"]),
            {
                "id",
                "title",
                "type",
                "funding_status",
                "target_amount_cents",
                "committed_cents",
                "deadline",
                "is_public",
            },
        )

    def test_the_response_is_not_cached(self):
        _, cookie = self.create_user(0)

        self.assertEqual(self.get(cookie).headers["cache-control"], "no-store")


class EmptyStateTest(UserCommitmentsTestCase):
    def test_a_user_without_commitments_gets_an_empty_list_and_zero_totals(self):
        _, cookie = self.create_user(500_00)

        self.assertEqual(self.get_ok(cookie), {"summary": EMPTY_SUMMARY, "commitments": []})

    def test_a_user_without_wallet_gets_the_empty_state_too(self):
        with self.Session() as db:
            user = User(email=f"{uuid4().hex}@example.com", hashed_password="x" * 60)
            db.add(user)
            db.flush()
            token = generate_session_token()
            db.add(UserSession(token=hash_session_token(token), user_id=user.id))
            db.commit()

        body = self.get_ok(f"{SESSION_COOKIE}={token}")

        self.assertEqual(body, {"summary": EMPTY_SUMMARY, "commitments": []})


class ListTest(UserCommitmentsTestCase):
    def test_each_commitment_carries_its_data_and_the_current_opportunity(self):
        _, cookie = self.create_user(500_00)
        deadline = datetime.now(UTC) + timedelta(days=30)
        opportunity_id = self.create_opportunity(deadline=deadline)
        created = self.commit(opportunity_id, cookie, 100_00)

        (item,) = self.get_ok(cookie)["commitments"]

        self.assertEqual(item["id"], created["id"])
        self.assertEqual(item["amount_cents"], 100_00)
        self.assertEqual(item["created_at"], created["created_at"])
        self.assertIsNone(item["estimated_equity"])
        opportunity = item["opportunity"]
        self.assertEqual(datetime.fromisoformat(opportunity.pop("deadline")), deadline)
        self.assertEqual(
            opportunity,
            {
                "id": opportunity_id,
                "title": "Piso en Girona",
                "type": "real_estate",
                "funding_status": "in_funding",
                "target_amount_cents": 72_000_00,
                # Progrés actual: ja inclou l'aportació acabada de comprometre.
                "committed_cents": 45_100_00,
                "is_public": True,
            },
        )

    def test_commitments_are_ordered_from_newest_to_oldest(self):
        _, cookie = self.create_user(1_000_00)
        first_opportunity = self.create_opportunity()
        second_opportunity = self.create_opportunity(title="Nave logística en Reus")
        now = datetime.now(UTC)
        oldest = self.commit(first_opportunity, cookie, 100_00)["id"]
        newest = self.commit(second_opportunity, cookie, 100_00)["id"]
        middle = self.commit(first_opportunity, cookie, 100_00)["id"]
        # Les dates no segueixen l'ordre de creació: mana la data, no l'identificador.
        self.set_created_at(oldest, now - timedelta(days=9))
        self.set_created_at(middle, now - timedelta(days=1))
        self.set_created_at(newest, now)

        body = self.get_ok(cookie)

        self.assertEqual([item["id"] for item in body["commitments"]], [newest, middle, oldest])

    def test_commitments_of_the_same_instant_keep_a_stable_order(self):
        _, cookie = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity()
        instant = datetime.now(UTC)
        ids = [self.commit(opportunity_id, cookie, 100_00)["id"] for _ in range(3)]
        for commitment_id in ids:
            self.set_created_at(commitment_id, instant)

        body = self.get_ok(cookie)

        self.assertEqual([item["id"] for item in body["commitments"]], sorted(ids, reverse=True))

    def test_several_commitments_in_one_opportunity_are_listed_separately(self):
        _, cookie = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity()
        first = self.commit(opportunity_id, cookie, 100_00)["id"]
        second = self.commit(opportunity_id, cookie, 250_00)["id"]
        self.set_created_at(first, datetime.now(UTC) - timedelta(days=1))

        body = self.get_ok(cookie)

        self.assertEqual(
            [(item["id"], item["amount_cents"]) for item in body["commitments"]],
            [(second, 250_00), (first, 100_00)],
        )
        self.assertEqual(
            {item["opportunity"]["id"] for item in body["commitments"]}, {opportunity_id}
        )
        # Tots dos mostren el mateix progrés actual de l'oportunitat.
        self.assertEqual(
            {item["opportunity"]["committed_cents"] for item in body["commitments"]},
            {45_350_00},
        )
        self.assertEqual(
            body["summary"],
            {"total_committed_cents": 350_00, "commitments_count": 2, "in_funding_count": 2},
        )


class EstimatedEquityTest(UserCommitmentsTestCase):
    def test_business_investments_show_the_estimated_equity(self):
        """Exemple de Trello: 1.000 € amb valoració de 2.700.000 € i objectiu de 300.000 €."""
        _, cookie = self.create_user(5_000_00)
        opportunity_id = self.create_opportunity(
            OpportunityType.EQUITY,
            title="Expansión de BioPack",
            target_amount_cents=300_000_00,
            committed_cents=184_500_00,
        )
        created = self.commit(opportunity_id, cookie, 1_000_00)

        (item,) = self.get_ok(cookie)["commitments"]

        self.assertEqual(item["opportunity"]["type"], "equity")
        equity = Decimal(item["estimated_equity"])
        self.assertEqual(equity, Decimal(1_000_00) / Decimal(3_000_000_00) * 100)
        self.assertEqual(round(equity, 3), Decimal("0.033"))
        # La mateixa xifra que va rebre en comprometre la inversió.
        self.assertEqual(equity, Decimal(created["estimated_equity"]))

    def test_real_estate_contributions_have_no_estimated_equity(self):
        _, cookie = self.create_user(500_00)
        self.commit(self.create_opportunity(), cookie, 100_00)

        (item,) = self.get_ok(cookie)["commitments"]

        self.assertIsNone(item["estimated_equity"])

    def test_a_business_opportunity_without_its_data_does_not_break_the_list(self):
        user_id, cookie = self.create_user(500_00)
        opportunity_id = self.create_opportunity(OpportunityType.EQUITY, specific_data=False)
        self.reserve(opportunity_id, user_id, 100_00)

        (item,) = self.get_ok(cookie)["commitments"]

        self.assertIsNone(item["estimated_equity"])
        self.assertFalse(item["opportunity"]["is_public"])


class FundingStatusTest(UserCommitmentsTestCase):
    def status_after(self, **changes) -> dict:
        """Compromet en una oportunitat en finançament, la canvia i en retorna l'estat llistat."""
        _, cookie = self.create_user(500_00)
        opportunity_id = self.create_opportunity()
        self.commit(opportunity_id, cookie, 100_00)
        self.update_opportunity(opportunity_id, **changes)
        (item,) = self.get_ok(cookie)["commitments"]
        return item["opportunity"]

    def test_shows_the_current_status_not_the_one_at_commitment_time(self):
        now = datetime.now(UTC)
        cases = {
            "funded": {"committed_cents": 72_000_00},
            "expired": {"deadline": now - timedelta(days=1)},
            "closed": {"status": OpportunityStatus.CLOSED, "date_closed": now},
        }
        for expected, changes in cases.items():
            with self.subTest(expected):
                opportunity = self.status_after(**changes)
                self.assertEqual(opportunity["funding_status"], expected)
                # Segueix tenint detall encara que ja no surti al catàleg.
                self.assertTrue(opportunity["is_public"])

    def test_reaching_the_target_shows_full_progress(self):
        user_id, cookie = self.create_user(500_00)
        opportunity_id = self.create_opportunity(committed_cents=71_900_00)
        self.commit(opportunity_id, cookie, 100_00)

        body = self.get_ok(cookie)

        opportunity = body["commitments"][0]["opportunity"]
        self.assertEqual(opportunity["funding_status"], "funded")
        self.assertEqual(opportunity["committed_cents"], opportunity["target_amount_cents"])
        self.assertEqual(body["summary"]["in_funding_count"], 0)
        catalog = self.client.get("/api/opportunities").json()
        self.assertNotIn(opportunity_id, [item["id"] for item in catalog])

    def test_a_funded_opportunity_stays_funded_after_the_deadline(self):
        opportunity = self.status_after(
            committed_cents=72_000_00, deadline=datetime.now(UTC) - timedelta(days=1)
        )

        self.assertEqual(opportunity["funding_status"], "funded")

    def test_a_rejected_opportunity_is_listed_without_public_detail(self):
        opportunity = self.status_after(status=OpportunityStatus.REJECTED)

        self.assertEqual(opportunity["funding_status"], "rejected")
        self.assertFalse(opportunity["is_public"])

    def test_a_commitment_in_a_rejected_opportunity_counts_in_the_total_only(self):
        _, cookie = self.create_user(500_00)
        opportunity_id = self.create_opportunity()
        self.commit(opportunity_id, cookie, 100_00)
        self.update_opportunity(opportunity_id, status=OpportunityStatus.REJECTED)

        summary = self.get_ok(cookie)["summary"]
        wallet = self.client.get("/api/me/wallet", headers={"Cookie": cookie}).json()

        # L'import segueix reservat al wallet, però l'oportunitat ja no està en finançament.
        self.assertEqual(
            summary,
            {"total_committed_cents": 100_00, "commitments_count": 1, "in_funding_count": 0},
        )
        self.assertEqual(summary["total_committed_cents"], wallet["committed_cents"])


class SummaryTest(UserCommitmentsTestCase):
    def test_summary_counts_commitments_and_those_in_funding(self):
        """Exemple de Trello: tres inversions que sumen 1.600,00 €, dues en finançament."""
        _, cookie = self.create_user(5_000_00)
        business = self.create_opportunity(
            OpportunityType.EQUITY, target_amount_cents=300_000_00, committed_cents=184_500_00
        )
        flat = self.create_opportunity()
        building = self.create_opportunity(
            target_amount_cents=400_000_00, committed_cents=399_500_00
        )
        self.commit(business, cookie, 1_000_00)
        self.commit(flat, cookie, 100_00)
        # Completa l'objectiu: l'oportunitat deixa d'estar en finançament.
        self.commit(building, cookie, 500_00)

        body = self.get_ok(cookie)

        self.assertEqual(
            body["summary"],
            {"total_committed_cents": 1_600_00, "commitments_count": 3, "in_funding_count": 2},
        )
        self.assertEqual(
            sorted(item["opportunity"]["funding_status"] for item in body["commitments"]),
            ["funded", "in_funding", "in_funding"],
        )

    def test_total_matches_the_committed_balance_of_the_wallet(self):
        user_id, cookie = self.create_user(5_000_00)
        still_open = self.create_opportunity()
        expired = self.create_opportunity()
        closed = self.create_opportunity()
        for opportunity_id, amount_cents in ((still_open, 100_00), (expired, 250_00), (closed, 75_50)):
            self.commit(opportunity_id, cookie, amount_cents)
        self.commit(still_open, cookie, 60_00)
        now = datetime.now(UTC)
        self.update_opportunity(expired, deadline=now - timedelta(days=1))
        self.update_opportunity(closed, status=OpportunityStatus.CLOSED, date_closed=now)

        summary = self.get_ok(cookie)["summary"]
        wallet = self.client.get("/api/me/wallet", headers={"Cookie": cookie}).json()

        # Els compromisos en oportunitats vençudes o tancades segueixen reservats.
        self.assertEqual(summary["total_committed_cents"], 485_50)
        self.assertEqual(summary["total_committed_cents"], wallet["committed_cents"])
        self.assertEqual(wallet["available_cents"], 5_000_00 - 485_50)
        self.assertEqual(summary["commitments_count"], 4)
        self.assertEqual(summary["in_funding_count"], 2)
        with self.Session() as db:
            stored = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
            self.assertEqual(stored.committed_cents, summary["total_committed_cents"])


class PendingReviewTest(UserCommitmentsTestCase):
    def create_pending_opportunity(self, user_id: int, initial_contribution_cents: int) -> int:
        """Una oportunitat pròpia pendent de revisió amb la seva aportació inicial."""
        opportunity_id = self.create_opportunity(
            user_id=user_id,
            status=OpportunityStatus.DRAFT,
            title="Local comercial en Sabadell",
            target_amount_cents=150_000_00,
            committed_cents=0,
            date_published=None,
        )
        self.reserve(opportunity_id, user_id, initial_contribution_cents)
        return opportunity_id

    def test_an_initial_contribution_pending_review_is_listed_without_public_detail(self):
        user_id, cookie = self.create_user(8_000_00, promoter=True)
        opportunity_id = self.create_pending_opportunity(user_id, 5_000_00)

        body = self.get_ok(cookie)

        (item,) = body["commitments"]
        self.assertEqual(item["amount_cents"], 5_000_00)
        opportunity = item["opportunity"]
        self.assertEqual(opportunity["id"], opportunity_id)
        self.assertEqual(opportunity["title"], "Local comercial en Sabadell")
        self.assertEqual(opportunity["funding_status"], "pending_review")
        self.assertFalse(opportunity["is_public"])
        self.assertEqual(opportunity["committed_cents"], 5_000_00)
        # Sense detall públic: el frontend no hi ha d'enllaçar.
        self.assertEqual(self.client.get(f"/api/opportunities/{opportunity_id}").status_code, 404)

    def test_a_pending_business_opportunity_shows_the_estimated_equity_too(self):
        """Tota inversió empresarial porta participació, també l'aportació inicial pròpia."""
        user_id, cookie = self.create_user(8_000_00, promoter=True)
        opportunity_id = self.create_opportunity(
            OpportunityType.EQUITY,
            user_id=user_id,
            status=OpportunityStatus.DRAFT,
            target_amount_cents=300_000_00,
            committed_cents=0,
            date_published=None,
        )
        self.reserve(opportunity_id, user_id, 5_000_00)

        (item,) = self.get_ok(cookie)["commitments"]

        self.assertEqual(item["opportunity"]["funding_status"], "pending_review")
        self.assertFalse(item["opportunity"]["is_public"])
        self.assertEqual(
            Decimal(item["estimated_equity"]),
            Decimal(5_000_00) / Decimal(3_000_000_00) * 100,
        )

    def test_it_counts_in_the_total_but_not_as_in_funding(self):
        user_id, cookie = self.create_user(8_000_00, promoter=True)
        self.create_pending_opportunity(user_id, 5_000_00)
        self.commit(self.create_opportunity(), cookie, 100_00)

        body = self.get_ok(cookie)
        wallet = self.client.get("/api/me/wallet", headers={"Cookie": cookie}).json()

        self.assertEqual(
            body["summary"],
            {"total_committed_cents": 5_100_00, "commitments_count": 2, "in_funding_count": 1},
        )
        self.assertEqual(wallet["committed_cents"], 5_100_00)
        self.assertEqual(wallet["available_cents"], 2_900_00)


if __name__ == "__main__":
    unittest.main()
