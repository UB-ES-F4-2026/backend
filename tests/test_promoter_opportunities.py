"""Consultar les oportunitats de l'entitat promotora autenticada (US05.2)."""
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
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

URL = "/api/me/opportunities"
EMPTY_SUMMARY = {
    "committed_cents": 0,
    "published_count": 0,
    "in_funding_count": 0,
    "pending_review_count": 0,
}
NOW = datetime.now(UTC)


class PromoterOpportunitiesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "promoter_opportunities_test_" + uuid4().hex
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

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def create_user(self, promoter: bool = True, available_cents: int = 0) -> tuple[int, str]:
        """Crea un usuari amb sessió iniciada; retorna el seu id i la cookie."""
        with self.Session() as db:
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
        self,
        user_id: int,
        opportunity_type=OpportunityType.REAL_ESTATE,
        specific_data=True,
        **changes,
    ) -> int:
        """Una oportunitat publicada i en finançament, tret del que indiquin `changes`."""
        values = {
            "user_id": user_id,
            "type": opportunity_type,
            "status": OpportunityStatus.PUBLISHED,
            "title": "Piso en Girona",
            "description": "Descripció.",
            "location": "Girona",
            "target_amount_cents": 72_000_00,
            "committed_cents": 0,
            "minimum_contribution_cents": 50_00,
            "deadline": NOW + timedelta(days=30),
            "date_published": NOW - timedelta(days=10),
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

    def create_draft(self, user_id: int, **changes) -> int:
        """Una oportunitat pendent de revisió, com les que crea `POST /api/opportunities`."""
        values = {"status": OpportunityStatus.DRAFT, "date_published": None}
        values.update(changes)
        return self.create_opportunity(user_id, **values)

    def create_closed(self, user_id: int, **changes) -> int:
        values = {"status": OpportunityStatus.CLOSED, "date_closed": NOW - timedelta(days=1)}
        values.update(changes)
        return self.create_opportunity(user_id, **values)

    def create_trello_example(self, user_id: int) -> None:
        """Tres publicades amb 475.100,00 € compromesos, una encara en finançament."""
        self.create_opportunity(
            user_id,
            title="Piso en Girona",
            committed_cents=45_100_00,
            date_published=NOW - timedelta(days=10),
        )
        self.create_opportunity(
            user_id,
            title="Rehabilitación de edificio en Lleida",
            target_amount_cents=400_000_00,
            committed_cents=400_000_00,
            date_published=NOW - timedelta(days=23),
        )
        self.create_opportunity(
            user_id,
            title="Nave logística en Reus",
            target_amount_cents=200_000_00,
            committed_cents=30_000_00,
            deadline=NOW - timedelta(days=12),
            date_published=NOW - timedelta(days=72),
        )

    def reserve(self, opportunity_id: int, user_id: int, amount_cents: int) -> None:
        with self.Session() as db:
            reserve_funds(
                db, user_id=user_id, opportunity_id=opportunity_id, amount_cents=amount_cents
            )
            db.commit()

    def get(self, cookie: str | None):
        return self.client.get(URL, headers={"Cookie": cookie} if cookie else {})

    def get_ok(self, cookie: str) -> dict:
        response = self.get(cookie)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def listed_ids(self, cookie: str) -> list[int]:
        return [item["id"] for item in self.get_ok(cookie)["opportunities"]]

    def profile_published_count(self, user_id: int) -> int:
        """«Proyectos publicados» del perfil públic de l'entitat."""
        entities = self.client.get("/api/promotingentity").json()
        return next(
            entity["published_projects_count"]
            for entity in entities
            if entity["user_id"] == user_id
        )


class AuthorizationTest(PromoterOpportunitiesTestCase):
    def test_requires_a_session(self):
        response = self.get(None)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid or missing session"})

    def test_a_user_without_promoting_entity_is_forbidden(self):
        _, cookie = self.create_user(promoter=False)

        response = self.get(cookie)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "A promoting entity is required"})

    def test_returns_only_the_opportunities_of_the_authenticated_entity(self):
        user_id, cookie = self.create_user()
        other_id, other_cookie = self.create_user()
        own = self.create_opportunity(user_id, committed_cents=100_00)
        own_draft = self.create_draft(user_id, created_at=NOW - timedelta(days=20))
        foreign = self.create_opportunity(other_id, committed_cents=900_00)
        foreign_draft = self.create_draft(other_id, created_at=NOW - timedelta(days=20))

        body = self.get_ok(cookie)
        other_body = self.get_ok(other_cookie)

        self.assertEqual([item["id"] for item in body["opportunities"]], [own, own_draft])
        self.assertEqual(body["summary"]["committed_cents"], 100_00)
        self.assertEqual(
            [item["id"] for item in other_body["opportunities"]], [foreign, foreign_draft]
        )
        self.assertEqual(other_body["summary"]["committed_cents"], 900_00)

    def test_the_response_is_not_cached(self):
        _, cookie = self.create_user()

        self.assertEqual(self.get(cookie).headers["cache-control"], "no-store")


class EmptyStateTest(PromoterOpportunitiesTestCase):
    def test_an_entity_without_opportunities_gets_an_empty_list_and_zero_totals(self):
        _, cookie = self.create_user()

        self.assertEqual(self.get_ok(cookie), {"summary": EMPTY_SUMMARY, "opportunities": []})

    def test_an_entity_with_only_rejected_opportunities_gets_the_empty_state(self):
        user_id, cookie = self.create_user()
        self.create_opportunity(
            user_id, status=OpportunityStatus.REJECTED, date_published=None, committed_cents=500_00
        )

        self.assertEqual(self.get_ok(cookie), {"summary": EMPTY_SUMMARY, "opportunities": []})


class ListTest(PromoterOpportunitiesTestCase):
    def test_each_opportunity_carries_the_data_shown_in_the_list(self):
        user_id, cookie = self.create_user()
        deadline = NOW + timedelta(days=33)
        date_published = NOW - timedelta(days=10)
        opportunity_id = self.create_opportunity(
            user_id,
            committed_cents=45_100_00,
            deadline=deadline,
            date_published=date_published,
        )

        (item,) = self.get_ok(cookie)["opportunities"]

        self.assertEqual(datetime.fromisoformat(item.pop("deadline")), deadline)
        self.assertEqual(datetime.fromisoformat(item.pop("date_published")), date_published)
        with self.Session() as db:
            created_at = db.get(Opportunity, opportunity_id).created_at
        self.assertEqual(datetime.fromisoformat(item.pop("created_at")), created_at)
        self.assertEqual(
            item,
            {
                "id": opportunity_id,
                "title": "Piso en Girona",
                "type": "real_estate",
                "funding_status": "in_funding",
                "target_amount_cents": 72_000_00,
                "committed_cents": 45_100_00,
                "investors_count": 0,
                "is_public": True,
            },
        )

    def test_both_opportunity_types_are_listed(self):
        user_id, cookie = self.create_user()
        self.create_opportunity(user_id, date_published=NOW - timedelta(days=2))
        self.create_opportunity(
            user_id, OpportunityType.EQUITY, date_published=NOW - timedelta(days=1)
        )

        types = [item["type"] for item in self.get_ok(cookie)["opportunities"]]

        self.assertEqual(types, ["equity", "real_estate"])

    def test_opportunities_are_ordered_from_most_recently_published(self):
        user_id, cookie = self.create_user()
        # Creades en un ordre diferent del de publicació: mana la data de publicació.
        middle = self.create_opportunity(user_id, date_published=NOW - timedelta(days=20))
        oldest = self.create_opportunity(user_id, date_published=NOW - timedelta(days=60))
        newest = self.create_opportunity(user_id, date_published=NOW - timedelta(days=2))

        self.assertEqual(self.listed_ids(cookie), [newest, middle, oldest])

    def test_opportunities_published_at_the_same_instant_keep_a_stable_order(self):
        user_id, cookie = self.create_user()
        instant = NOW - timedelta(days=3)
        ids = [self.create_opportunity(user_id, date_published=instant) for _ in range(3)]

        self.assertEqual(self.listed_ids(cookie), sorted(ids, reverse=True))

    def test_funded_expired_and_closed_opportunities_stay_listed(self):
        user_id, cookie = self.create_user()
        in_funding = self.create_opportunity(user_id, date_published=NOW - timedelta(days=1))
        funded = self.create_opportunity(
            user_id, committed_cents=72_000_00, date_published=NOW - timedelta(days=2)
        )
        expired = self.create_opportunity(
            user_id, deadline=NOW - timedelta(days=1), date_published=NOW - timedelta(days=3)
        )
        closed = self.create_closed(user_id, date_published=NOW - timedelta(days=4))
        funded_past_deadline = self.create_opportunity(
            user_id,
            committed_cents=72_000_00,
            deadline=NOW - timedelta(days=1),
            date_published=NOW - timedelta(days=5),
        )

        body = self.get_ok(cookie)

        self.assertEqual(
            [(item["id"], item["funding_status"]) for item in body["opportunities"]],
            [
                (in_funding, "in_funding"),
                (funded, "funded"),
                (expired, "expired"),
                (closed, "closed"),
                (funded_past_deadline, "funded"),
            ],
        )
        # Totes tenen detall, encara que el catàleg ja només mostri la primera.
        self.assertTrue(all(item["is_public"] for item in body["opportunities"]))
        catalog = [item["id"] for item in self.client.get("/api/opportunities").json()]
        self.assertIn(in_funding, catalog)
        for opportunity_id in (funded, expired, closed, funded_past_deadline):
            self.assertNotIn(opportunity_id, catalog)
            detail = self.client.get(f"/api/opportunities/{opportunity_id}")
            self.assertEqual(detail.status_code, 200)

    def test_a_published_opportunity_rejected_later_stays_listed_as_rejected(self):
        """Compta com a projecte publicat al perfil, així que no pot desaparèixer de la llista."""
        user_id, cookie = self.create_user()
        opportunity_id = self.create_opportunity(user_id, status=OpportunityStatus.REJECTED)

        (item,) = self.get_ok(cookie)["opportunities"]

        self.assertEqual(item["id"], opportunity_id)
        self.assertEqual(item["funding_status"], "rejected")
        self.assertFalse(item["is_public"])

    def test_a_published_opportunity_without_its_type_data_has_no_public_detail(self):
        user_id, cookie = self.create_user()
        opportunity_id = self.create_opportunity(
            user_id, OpportunityType.EQUITY, specific_data=False
        )

        (item,) = self.get_ok(cookie)["opportunities"]

        self.assertEqual(item["id"], opportunity_id)
        self.assertEqual(item["funding_status"], "in_funding")
        # El detall públic no la troba, així que el frontend no hi ha d'enllaçar.
        self.assertFalse(item["is_public"])
        self.assertEqual(self.client.get(f"/api/opportunities/{opportunity_id}").status_code, 404)

    def test_never_published_rejected_opportunities_are_not_listed(self):
        user_id, cookie = self.create_user()
        published = self.create_opportunity(user_id)
        self.create_opportunity(user_id, status=OpportunityStatus.REJECTED, date_published=None)

        self.assertEqual(self.listed_ids(cookie), [published])


class InvestorsCountTest(PromoterOpportunitiesTestCase):
    def test_counts_distinct_investors_without_exposing_who_they_are(self):
        user_id, cookie = self.create_user()
        opportunity_id = self.create_opportunity(user_id)
        other_opportunity = self.create_opportunity(
            user_id, date_published=NOW - timedelta(days=30)
        )
        first_investor, _ = self.create_user(promoter=False, available_cents=1_000_00)
        second_investor, _ = self.create_user(promoter=False, available_cents=1_000_00)
        # Dues aportacions del mateix usuari compten com un sol inversor.
        self.reserve(opportunity_id, first_investor, 100_00)
        self.reserve(opportunity_id, first_investor, 200_00)
        self.reserve(opportunity_id, second_investor, 300_00)
        self.reserve(other_opportunity, second_investor, 50_00)

        response = self.get(cookie)
        body = response.json()

        self.assertEqual(
            [
                (item["id"], item["investors_count"], item["committed_cents"])
                for item in body["opportunities"]
            ],
            [(opportunity_id, 2, 600_00), (other_opportunity, 1, 50_00)],
        )
        self.assertEqual(
            set(body["opportunities"][0]),
            {
                "id",
                "title",
                "type",
                "funding_status",
                "target_amount_cents",
                "committed_cents",
                "investors_count",
                "deadline",
                "date_published",
                "created_at",
                "is_public",
            },
        )
        self.assertEqual(set(body), {"summary", "opportunities"})
        # Cap dada dels inversors a la resposta: ni identificadors ni correus.
        with self.Session() as db:
            emails = [db.get(User, investor).email for investor in (first_investor, second_investor)]
        for email in emails:
            self.assertNotIn(email, response.text)

    def test_the_initial_contribution_of_the_promoter_counts_as_one_investor(self):
        """US06.1.1: 5.000,00 € d'aportació inicial mostren 5.000,00 € i 1 inversor."""
        user_id, cookie = self.create_user(available_cents=8_000_00)
        opportunity_id = self.create_draft(user_id, target_amount_cents=150_000_00)
        self.reserve(opportunity_id, user_id, 5_000_00)

        (item,) = self.get_ok(cookie)["opportunities"]

        self.assertEqual(item["committed_cents"], 5_000_00)
        self.assertEqual(item["investors_count"], 1)


class SummaryTest(PromoterOpportunitiesTestCase):
    def test_summary_adds_up_the_published_opportunities(self):
        user_id, cookie = self.create_user()
        self.create_trello_example(user_id)

        body = self.get_ok(cookie)

        self.assertEqual(
            body["summary"],
            {
                "committed_cents": 475_100_00,
                "published_count": 3,
                "in_funding_count": 1,
                "pending_review_count": 0,
            },
        )
        self.assertEqual(
            [item["funding_status"] for item in body["opportunities"]],
            ["in_funding", "funded", "expired"],
        )

    def test_closed_opportunities_count_as_published_but_not_in_funding(self):
        user_id, cookie = self.create_user()
        self.create_closed(user_id, committed_cents=10_000_00)

        self.assertEqual(
            self.get_ok(cookie)["summary"],
            {
                "committed_cents": 10_000_00,
                "published_count": 1,
                "in_funding_count": 0,
                "pending_review_count": 0,
            },
        )

    def test_published_count_matches_the_entity_profile(self):
        user_id, cookie = self.create_user()
        self.create_trello_example(user_id)
        self.create_closed(user_id)
        self.create_draft(user_id)
        self.create_opportunity(user_id, status=OpportunityStatus.REJECTED, date_published=None)
        # Publicada i després retirada: el perfil la segueix comptant com a projecte publicat.
        self.create_opportunity(
            user_id, status=OpportunityStatus.REJECTED, committed_cents=1_000_00
        )

        summary = self.get_ok(cookie)["summary"]

        self.assertEqual(summary["published_count"], 5)
        self.assertEqual(summary["published_count"], self.profile_published_count(user_id))
        # El capital segueix el mateix criteri que el recompte: suma el de totes les publicades.
        self.assertEqual(summary["committed_cents"], 475_100_00 + 1_000_00)
        self.assertEqual(summary["in_funding_count"], 1)
        self.assertEqual(summary["pending_review_count"], 1)

    def test_published_count_matches_the_profile_of_an_entity_without_opportunities(self):
        user_id, cookie = self.create_user()

        summary = self.get_ok(cookie)["summary"]

        self.assertEqual(summary["published_count"], 0)
        self.assertEqual(self.profile_published_count(user_id), 0)


class PendingReviewTest(PromoterOpportunitiesTestCase):
    def test_a_pending_opportunity_is_listed_without_public_detail(self):
        user_id, cookie = self.create_user(available_cents=8_000_00)
        opportunity_id = self.create_draft(
            user_id, title="Local comercial en Sabadell", target_amount_cents=150_000_00
        )
        self.reserve(opportunity_id, user_id, 5_000_00)

        (item,) = self.get_ok(cookie)["opportunities"]

        self.assertEqual(item["id"], opportunity_id)
        self.assertEqual(item["title"], "Local comercial en Sabadell")
        self.assertEqual(item["funding_status"], "pending_review")
        self.assertIsNone(item["date_published"])
        self.assertIsNotNone(item["created_at"])
        self.assertFalse(item["is_public"])
        self.assertEqual(self.client.get(f"/api/opportunities/{opportunity_id}").status_code, 404)

    def test_pending_opportunities_have_their_own_count_and_stay_out_of_the_totals(self):
        """Mockup de la US06.1.1: el capital compromès no suma l'aportació inicial pendent."""
        user_id, cookie = self.create_user(available_cents=8_000_00)
        self.create_trello_example(user_id)
        opportunity_id = self.create_draft(user_id, target_amount_cents=150_000_00)
        self.reserve(opportunity_id, user_id, 5_000_00)

        summary = self.get_ok(cookie)["summary"]

        self.assertEqual(
            summary,
            {
                "committed_cents": 475_100_00,
                "published_count": 3,
                "in_funding_count": 1,
                "pending_review_count": 1,
            },
        )
        self.assertEqual(summary["published_count"], self.profile_published_count(user_id))

    def test_a_pending_opportunity_is_ordered_by_its_creation_date(self):
        user_id, cookie = self.create_user()
        published_recently = self.create_opportunity(
            user_id, date_published=NOW - timedelta(days=2)
        )
        published_long_ago = self.create_opportunity(
            user_id, date_published=NOW - timedelta(days=40)
        )
        new_draft = self.create_draft(user_id, created_at=NOW)
        old_draft = self.create_draft(user_id, created_at=NOW - timedelta(days=15))

        self.assertEqual(
            self.listed_ids(cookie),
            [new_draft, published_recently, old_draft, published_long_ago],
        )

    def test_a_pending_opportunity_is_never_in_funding(self):
        user_id, cookie = self.create_user()
        # Amb capital pendent i termini obert, però sense publicar.
        self.create_draft(user_id)

        body = self.get_ok(cookie)

        self.assertEqual(body["summary"]["in_funding_count"], 0)
        self.assertEqual(body["summary"]["pending_review_count"], 1)
        self.assertEqual(body["opportunities"][0]["funding_status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
