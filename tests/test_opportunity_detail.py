"""Detalle público de una oportunidad inmobiliaria (US02.2.1)."""
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.main import app
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.real_estate_opportunity import (
    AssetType,
    IntendedUse,
    RealEstateOpportunity,
    RealEstatePurpose,
)
from app.models.user import User

DETAIL_KEYS = {
    "id", "type", "status", "title", "description", "location", "cover_image_url",
    "target_amount_cents", "committed_cents", "minimum_contribution_cents",
    "deadline", "date_published", "promoter", "real_estate", "server_time",
}


class OpportunityDetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "opportunity_detail_test_" + uuid4().hex
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
        # Sin cookie de sesión: el detalle es público.
        cls.client = TestClient(app, base_url="https://testserver")

        with cls.Session() as db:
            user = User(email="promoter@example.com", hashed_password="x" * 60)
            db.add(user)
            db.flush()
            db.add(PromotingEntity(
                user_id=user.id,
                legal_name="Promociones Girona SL",
                image_url="https://example.com/logo.png",
                experience_years=0,
                location="Girona, Girona, España",
            ))
            db.commit()
            cls.promoter_id = user.id

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def create_opportunity(self, real_estate=True, **changes) -> int:
        values = {
            "user_id": self.promoter_id,
            "type": OpportunityType.REAL_ESTATE,
            "status": OpportunityStatus.PUBLISHED,
            "title": "Rehabilitación de edificio",
            "description": "Primer párrafo.\n\nSegundo párrafo.",
            "location": "Girona, Girona, España",
            "cover_image_url": "https://example.com/edificio.jpg",
            "target_amount_cents": 250_000_00,
            "committed_cents": 100_000_00,
            "minimum_contribution_cents": 500_00,
            "deadline": datetime(2030, 1, 15, 18, 0, tzinfo=UTC),
            "date_published": datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
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
                public_latitude=Decimal("41.981800"),
                public_longitude=Decimal("2.823700"),
            )
        with self.Session() as db:
            db.add(opportunity)
            db.commit()
            return opportunity.id

    def get(self, opportunity_id):
        return self.client.get(f"/api/opportunities/{opportunity_id}")

    def test_returns_the_full_detail_contract(self):
        opportunity_id = self.create_opportunity()
        before = datetime.now(UTC)

        response = self.get(opportunity_id)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), DETAIL_KEYS)
        self.assertEqual(body["id"], opportunity_id)
        self.assertEqual(body["type"], "real_estate")
        self.assertEqual(body["status"], "published")
        self.assertEqual(body["description"], "Primer párrafo.\n\nSegundo párrafo.")
        self.assertEqual(body["target_amount_cents"], 250_000_00)
        self.assertEqual(body["committed_cents"], 100_000_00)
        self.assertEqual(body["minimum_contribution_cents"], 500_00)
        self.assertEqual(datetime.fromisoformat(body["deadline"]),
                         datetime(2030, 1, 15, 18, 0, tzinfo=UTC))
        self.assertEqual(body["promoter"], {
            "user_id": self.promoter_id,
            "legal_name": "Promociones Girona SL",
            "image_url": "https://example.com/logo.png",
            "published_projects_count": body["promoter"]["published_projects_count"],
            "experience_years": 0,
            "location": "Girona, Girona, España",
        })
        self.assertGreaterEqual(body["promoter"]["published_projects_count"], 1)
        # Los Decimal se serializan como texto para no perder precisión.
        self.assertEqual(body["real_estate"], {
            "purpose": "acquisition_and_renovation",
            "intended_use": "rental",
            "asset_type": "residential",
            "surface_m2": "950.50",
            "planned_housing_units": 12,
            "estimated_works_end": "2027-06-30",
            "estimated_rental_start": "2027-09-01",
            "public_latitude": "41.981800",
            "public_longitude": "2.823700",
        })
        server_time = datetime.fromisoformat(body["server_time"])
        self.assertLessEqual(before, server_time)
        self.assertLessEqual(server_time, datetime.now(UTC))

    def test_optional_values_are_null(self):
        opportunity_id = self.create_opportunity(minimum_contribution_cents=None)
        with self.Session() as db:
            real_estate = db.get(RealEstateOpportunity, opportunity_id)
            real_estate.purpose = RealEstatePurpose.ACQUISITION
            real_estate.intended_use = IntendedUse.OWN_USE
            real_estate.asset_type = AssetType.LAND
            real_estate.planned_housing_units = None
            real_estate.estimated_works_end = None
            real_estate.estimated_rental_start = None
            real_estate.public_latitude = None
            real_estate.public_longitude = None
            db.commit()

        body = self.get(opportunity_id).json()

        self.assertIsNone(body["minimum_contribution_cents"])
        for field in ("planned_housing_units", "estimated_works_end",
                      "estimated_rental_start", "public_latitude", "public_longitude"):
            self.assertIsNone(body["real_estate"][field], field)

    def test_finished_opportunities_remain_accessible(self):
        now = datetime.now(UTC)
        cases = {
            "closed": {"status": OpportunityStatus.CLOSED, "date_closed": now},
            "funded": {"committed_cents": 250_000_00},
            "over-funded": {"committed_cents": 300_000_00},
            "expired": {"deadline": now - timedelta(minutes=1)},
        }
        for name, changes in cases.items():
            with self.subTest(name):
                response = self.get(self.create_opportunity(**changes))
                self.assertEqual(response.status_code, 200)
        closed = self.get(self.create_opportunity(**cases["closed"])).json()
        self.assertEqual(closed["status"], "closed")

    def test_non_public_opportunities_get_the_same_not_found_response(self):
        unknown = self.get(999_999)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json(), {"detail": "Oportunidad no disponible"})

        cases = {
            "draft": {"status": OpportunityStatus.DRAFT, "date_published": None},
            "rejected": {"status": OpportunityStatus.REJECTED, "date_published": None},
            "equity": {"type": OpportunityType.EQUITY, "real_estate": False},
            "real estate without property data": {"real_estate": False},
        }
        for name, changes in cases.items():
            with self.subTest(name):
                response = self.get(self.create_opportunity(**changes))
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), unknown.json())

    def test_does_not_expose_private_or_internal_data(self):
        body = self.get(self.create_opportunity()).json()
        flat = str(body)
        self.assertNotIn("promoter@example.com", flat)
        self.assertNotIn("hashed_password", flat)
        for internal in ("user_id", "created_at", "updated_at", "date_closed"):
            self.assertNotIn(internal, body)


if __name__ == "__main__":
    unittest.main()
