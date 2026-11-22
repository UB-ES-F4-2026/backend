"""Create and read investment opportunities through the API."""
import json
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user, get_optional_current_user
from app.core import media
from app.database import engine, get_db
from app.main import app
from app.models.business_opportunity import BusinessPhase, BusinessSector
from app.models.commitment import Commitment
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.opportunity_image import OpportunityImage
from app.models.promoting_entity import PromotingEntity
from app.models.real_estate_opportunity import (
    AssetType,
    IntendedUse,
    RealEstatePurpose,
)
from app.models.user import User
from app.models.wallet import Wallet


class OpportunitiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = TemporaryDirectory()
        cls.previous_media_root = media.MEDIA_ROOT
        media.MEDIA_ROOT = Path(cls.media_directory.name)
        cls.database = "opportunities_test_" + uuid4().hex
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

        cls.session = Session()
        cls.user = User(
            email="creator@example.com",
            hashed_password="x" * 60,
        )
        cls.session.add(cls.user)
        cls.session.commit()
        cls.session.refresh(cls.user)
        cls.session.add(PromotingEntity(user_id=cls.user.id, legal_name="Creator SL"))
        cls.session.commit()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: cls.user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.session.close()
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))
        media.MEDIA_ROOT = cls.previous_media_root
        cls.media_directory.cleanup()

    def opportunity_body(self, **changes):
        body = {
            "type": "real_estate",
            "title": "Investment opportunity",
            "description": "A test opportunity",
            "location": {
                "municipality": "Barcelona",
                "province": "Barcelona",
                "country": "Spain",
            },
            "target_amount_cents": 25000000,
            "minimum_contribution_cents": 5000,
            "deadline": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "real_estate": {
                "purpose": "acquisition_and_renovation",
                "intended_use": "rental",
                "asset_type": "residential",
                "surface_m2": "250.50",
                "planned_housing_units": 4,
                "estimated_works_end": "2027-01-15",
                "estimated_rental_start": "2027-03-01",
                "public_latitude": "41.387000",
                "public_longitude": "2.170000",
            },
        }
        body.update(changes)
        return body

    def set_wallet_balance(self, available_cents: int) -> None:
        wallet = self.session.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
        if wallet is None:
            self.session.add(Wallet(user_id=self.user.id, available_cents=available_cents))
        else:
            wallet.available_cents = available_cents
            wallet.committed_cents = 0
        self.session.commit()

    def business_opportunity_body(self, **changes):
        body = self.opportunity_body(type="equity", real_estate=None)
        body["business"] = {
            "sector": "technology",
            "phase": "growth",
            "pre_investment_valuation_cents": 135000000,
        }
        body.update(changes)
        return body

    def post_opportunity(self, body: dict, images=None):
        image_files = images if images is not None else [
            ("image.png", b"\x89PNG\r\n\x1a\nimage", "image/png"),
        ]
        files = [("metadata", (None, json.dumps(body)))]
        files.extend(("images", image) for image in image_files)
        return self.client.post("/api/opportunities", files=files)

    def test_create_opportunity_requires_authentication(self):
        app.dependency_overrides.pop(get_current_user)
        response = self.post_opportunity(self.opportunity_body())
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.assertEqual(response.status_code, 401)

    def test_create_opportunity_assigns_current_user(self):
        response = self.post_opportunity(self.opportunity_body())

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["user_id"], self.user.id)
        self.assertEqual(body["committed_cents"], 0)
        self.assertEqual(body["type"], "real_estate")
        self.assertIsNone(body["date_published"])
        self.assertNotIn("status", body)
        self.session.expire_all()
        opportunity = self.session.get(Opportunity, body["id"])
        self.assertEqual(opportunity.status, OpportunityStatus.DRAFT)
        self.assertEqual(opportunity.location, "Barcelona, Barcelona, Spain")
        self.assertEqual(opportunity.minimum_contribution_cents, 5000)
        real_estate = opportunity.real_estate
        self.assertEqual(
            real_estate.purpose,
            RealEstatePurpose.ACQUISITION_AND_RENOVATION,
        )
        self.assertEqual(real_estate.intended_use, IntendedUse.RENTAL)
        self.assertEqual(real_estate.asset_type, AssetType.RESIDENTIAL)
        self.assertEqual(real_estate.surface_m2, Decimal("250.50"))
        self.assertEqual(real_estate.planned_housing_units, 4)
        self.assertEqual(real_estate.estimated_works_end, date(2027, 1, 15))
        self.assertEqual(real_estate.estimated_rental_start, date(2027, 3, 1))
        self.assertEqual(real_estate.public_latitude, Decimal("41.387000"))
        self.assertEqual(real_estate.public_longitude, Decimal("2.170000"))
        self.assertEqual(len(body["images"]), 1)
        self.assertEqual(body["cover_image_url"], body["images"][0]["url"])
        image = self.session.scalar(
            select(OpportunityImage).where(OpportunityImage.opportunity_id == body["id"])
        )
        self.assertEqual(image.position, 0)
        self.assertEqual(image.size_bytes, len(b"\x89PNG\r\n\x1a\nimage"))
        catalog = self.client.get("/api/opportunities")
        self.assertNotIn(body["id"], [item["id"] for item in catalog.json()])

    def test_create_opportunity_requires_promoting_entity(self):
        user = User(email="no-promoter@example.com", hashed_password="x" * 60)
        self.session.add(user)
        self.session.commit()
        app.dependency_overrides[get_current_user] = lambda: user
        response = self.post_opportunity(self.opportunity_body())
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.assertEqual(response.status_code, 403)

    def test_create_business_opportunity_persists_business_data(self):
        response = self.post_opportunity(self.business_opportunity_body())

        self.assertEqual(response.status_code, 201)
        opportunity_id = response.json()["id"]
        self.session.expire_all()
        opportunity = self.session.get(Opportunity, opportunity_id)
        self.assertEqual(opportunity.status, OpportunityStatus.DRAFT)
        self.assertIsNone(opportunity.date_published)
        self.assertEqual(opportunity.business.sector, BusinessSector.TECHNOLOGY)
        self.assertEqual(opportunity.business.phase, BusinessPhase.GROWTH)
        self.assertEqual(
            opportunity.business.pre_investment_valuation_cents,
            135000000,
        )
        catalog = self.client.get("/api/opportunities")
        self.assertNotIn(opportunity_id, [item["id"] for item in catalog.json()])

    def test_create_opportunity_rejects_invalid_data(self):
        invalid_bodies = (
            self.opportunity_body(type="invalid"),
            self.opportunity_body(target_amount_cents=0),
            self.opportunity_body(minimum_contribution_cents=0),
            self.opportunity_body(minimum_contribution_cents=25000001),
            self.opportunity_body(initial_contribution_cents=4999),
            self.opportunity_body(initial_contribution_cents=25000001),
            self.opportunity_body(target_amount_cents=5000.0),
            self.opportunity_body(title=" "),
            self.opportunity_body(description=" "),
            self.opportunity_body(location={"municipality": " ", "province": "A", "country": "B"}),
            self.opportunity_body(location={"municipality": "A", "province": " ", "country": "B"}),
            self.opportunity_body(location={"municipality": "A", "province": "B", "country": " "}),
            self.opportunity_body(deadline=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()),
        )

        for body in invalid_bodies:
            with self.subTest(body=body):
                response = self.post_opportunity(body)
                self.assertEqual(response.status_code, 422)

    def test_create_opportunity_validates_images(self):
        invalid_images = (
            [],
            [("text.txt", b"not-an-image", "text/plain")],
            [
                (
                    "large.png",
                    b"\x89PNG\r\n\x1a\n" + b"x" * (media.MAX_IMAGE_BYTES + 1),
                    "image/png",
                )
            ],
        )

        for images in invalid_images:
            with self.subTest(images=images):
                response = self.post_opportunity(self.opportunity_body(), images=images)
                self.assertEqual(response.status_code, 422)

    def test_create_opportunity_validates_real_estate_data(self):
        invalid_real_estate = (
            None,
            {**self.opportunity_body()["real_estate"], "surface_m2": "0"},
            {
                **self.opportunity_body()["real_estate"],
                "planned_housing_units": None,
            },
            {
                **self.opportunity_body()["real_estate"],
                "asset_type": "commercial",
            },
            {
                **self.opportunity_body()["real_estate"],
                "purpose": "acquisition",
            },
            {
                **self.opportunity_body()["real_estate"],
                "intended_use": "sale",
            },
            {
                **self.opportunity_body()["real_estate"],
                "public_longitude": None,
            },
            {
                **self.opportunity_body()["real_estate"],
                "public_latitude": "91",
            },
        )

        for real_estate in invalid_real_estate:
            with self.subTest(real_estate=real_estate):
                response = self.post_opportunity(
                    self.opportunity_body(real_estate=real_estate)
                )
                self.assertEqual(response.status_code, 422)

    def test_create_opportunity_validates_business_data(self):
        invalid_business = (
            None,
            {
                **self.business_opportunity_body()["business"],
                "pre_investment_valuation_cents": 0,
            },
            {
                **self.business_opportunity_body()["business"],
                "pre_investment_valuation_cents": 1.5,
            },
            {**self.business_opportunity_body()["business"], "sector": "invalid"},
            {**self.business_opportunity_body()["business"], "phase": "invalid"},
        )

        for business in invalid_business:
            with self.subTest(business=business):
                response = self.post_opportunity(
                    self.business_opportunity_body(business=business)
                )
                self.assertEqual(response.status_code, 422)

        response = self.post_opportunity(
            self.opportunity_body(
                business=self.business_opportunity_body()["business"]
            )
        )
        self.assertEqual(response.status_code, 422)

    def test_create_business_opportunity_accepts_trello_sectors_and_phases(self):
        sectors = [sector.value for sector in BusinessSector]
        phases = [phase.value for phase in BusinessPhase]

        for index, sector in enumerate(sectors):
            with self.subTest(sector=sector):
                response = self.post_opportunity(
                    self.business_opportunity_body(
                        title=f"Business sector {index}",
                        business={
                            **self.business_opportunity_body()["business"],
                            "sector": sector,
                        },
                    )
                )
                self.assertEqual(response.status_code, 201)

        for index, phase in enumerate(phases):
            with self.subTest(phase=phase):
                response = self.post_opportunity(
                    self.business_opportunity_body(
                        title=f"Business phase {index}",
                        business={
                            **self.business_opportunity_body()["business"],
                            "phase": phase,
                        },
                    )
                )
                self.assertEqual(response.status_code, 201)

    def test_create_opportunity_accepts_valid_real_estate_variants(self):
        base_real_estate = self.opportunity_body()["real_estate"]
        valid_real_estate = (
            {
                **base_real_estate,
                "asset_type": "mixed",
                "planned_housing_units": 2,
            },
            {
                **base_real_estate,
                "purpose": "acquisition",
                "intended_use": "sale",
                "asset_type": "commercial",
                "planned_housing_units": None,
                "estimated_works_end": None,
                "estimated_rental_start": None,
                "public_latitude": None,
                "public_longitude": None,
            },
        )

        for index, real_estate in enumerate(valid_real_estate):
            with self.subTest(real_estate=real_estate):
                response = self.post_opportunity(
                    self.opportunity_body(
                        title=f"Valid real estate opportunity {index}",
                        real_estate=real_estate,
                    )
                )
                self.assertEqual(response.status_code, 201)

    def test_database_failure_removes_stored_images(self):
        class FailingCommitSession:
            def __init__(self, session):
                self.session = session

            def commit(self):
                raise RuntimeError("Database commit failed")

            def __getattr__(self, name):
                return getattr(self.session, name)

        previous_override = app.dependency_overrides[get_db]

        def override_get_db():
            yield FailingCommitSession(self.session)

        files_before = {
            path.relative_to(media.MEDIA_ROOT)
            for path in media.MEDIA_ROOT.rglob("*")
            if path.is_file()
        }
        app.dependency_overrides[get_db] = override_get_db
        try:
            with self.assertRaisesRegex(RuntimeError, "Database commit failed"):
                self.post_opportunity(self.opportunity_body())
        finally:
            app.dependency_overrides[get_db] = previous_override

        files_after = {
            path.relative_to(media.MEDIA_ROOT)
            for path in media.MEDIA_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files_after, files_before)

    def test_initial_contribution_reserves_funds_with_the_new_opportunity(self):
        self.set_wallet_balance(10000)

        response = self.post_opportunity(
            self.opportunity_body(initial_contribution_cents=7500)
        )

        self.assertEqual(response.status_code, 201)
        opportunity_id = response.json()["id"]
        self.session.expire_all()
        wallet = self.session.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
        opportunity = self.session.get(Opportunity, opportunity_id)
        commitment = self.session.scalar(
            select(Commitment).where(Commitment.opportunity_id == opportunity_id)
        )
        self.assertEqual((wallet.available_cents, wallet.committed_cents), (2500, 7500))
        self.assertEqual(opportunity.committed_cents, 7500)
        self.assertEqual(opportunity.status, OpportunityStatus.DRAFT)
        self.assertEqual(commitment.amount_cents, 7500)

    def test_business_initial_contribution_reserves_funds_with_the_new_opportunity(self):
        self.set_wallet_balance(800000)

        response = self.post_opportunity(
            self.business_opportunity_body(initial_contribution_cents=500000)
        )

        self.assertEqual(response.status_code, 201)
        opportunity_id = response.json()["id"]
        self.session.expire_all()
        wallet = self.session.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
        opportunity = self.session.get(Opportunity, opportunity_id)
        commitment = self.session.scalar(
            select(Commitment).where(Commitment.opportunity_id == opportunity_id)
        )
        self.assertEqual(
            (wallet.available_cents, wallet.committed_cents),
            (300000, 500000),
        )
        self.assertEqual(opportunity.committed_cents, 500000)
        self.assertEqual(opportunity.status, OpportunityStatus.DRAFT)
        self.session.delete(commitment)
        self.session.delete(opportunity)
        self.session.commit()

    def test_business_detail_calculates_equity_offered(self):
        response = self.post_opportunity(
            self.business_opportunity_body(target_amount_cents=15000000)
        )

        self.assertEqual(response.status_code, 201)
        opportunity_id = response.json()["id"]
        opportunity = self.session.get(Opportunity, opportunity_id)
        opportunity.status = OpportunityStatus.PUBLISHED
        opportunity.date_published = datetime.now(UTC)
        self.session.commit()

        detail = self.client.get(f"/api/opportunities/{opportunity_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(Decimal(detail.json()["business"]["equity_offered"]), Decimal("10"))
        opportunity.status = OpportunityStatus.DRAFT
        opportunity.date_published = None
        self.session.commit()

    def test_opportunity_images_keep_their_order_and_access_rules(self):
        response = self.post_opportunity(
            self.opportunity_body(),
            images=[
                ("cover.png", b"\x89PNG\r\n\x1a\ncover", "image/png"),
                ("gallery.webp", b"RIFF\x00\x00\x00\x00WEBPimage", "image/webp"),
            ],
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual([image["position"] for image in body["images"]], [0, 1])
        cover_url = body["cover_image_url"]
        self.assertEqual(self.client.get(cover_url).status_code, 404)

        app.dependency_overrides[get_optional_current_user] = lambda: self.user
        owner_response = self.client.get(cover_url)
        app.dependency_overrides.pop(get_optional_current_user)
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(owner_response.headers["content-type"], "image/png")
        self.assertEqual(owner_response.content, b"\x89PNG\r\n\x1a\ncover")

        opportunity = self.session.get(Opportunity, body["id"])
        opportunity.status = OpportunityStatus.PUBLISHED
        opportunity.date_published = datetime.now(UTC)
        self.session.commit()
        self.assertEqual(self.client.get(cover_url).status_code, 200)

    def test_insufficient_initial_contribution_does_not_create_partial_data(self):
        self.set_wallet_balance(5000)
        commitments_before = self.session.scalar(select(func.count()).select_from(Commitment))

        response = self.post_opportunity(
            self.opportunity_body(
                title="Rollback opportunity", initial_contribution_cents=7500
            )
        )

        self.assertEqual(response.status_code, 409)
        self.session.expire_all()
        wallet = self.session.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
        opportunity = self.session.scalar(
            select(Opportunity).where(Opportunity.title == "Rollback opportunity")
        )
        self.assertEqual((wallet.available_cents, wallet.committed_cents), (5000, 0))
        self.assertIsNone(opportunity)
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Commitment)),
            commitments_before,
        )

    def test_insufficient_business_initial_contribution_does_not_create_partial_data(self):
        self.set_wallet_balance(800000)
        commitments_before = self.session.scalar(select(func.count()).select_from(Commitment))

        response = self.post_opportunity(
            self.business_opportunity_body(
                title="Business rollback opportunity",
                initial_contribution_cents=900000,
            )
        )

        self.assertEqual(response.status_code, 409)
        self.session.expire_all()
        wallet = self.session.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
        opportunity = self.session.scalar(
            select(Opportunity).where(Opportunity.title == "Business rollback opportunity")
        )
        self.assertEqual((wallet.available_cents, wallet.committed_cents), (800000, 0))
        self.assertIsNone(opportunity)
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Commitment)),
            commitments_before,
        )

    def create_database_opportunity(self, **changes):
        values = {
            "user_id": self.user.id,
            "type": "real_estate",
            "status": OpportunityStatus.PUBLISHED,
            "title": "Database opportunity",
            "description": "A database opportunity",
            "location": "Barcelona",
            "target_amount_cents": 10000,
            "committed_cents": 0,
            "deadline": datetime.now(UTC) + timedelta(days=30),
            "date_published": datetime.now(UTC),
        }
        values.update(changes)
        opportunity = Opportunity(**values)
        self.session.add(opportunity)
        self.session.commit()
        self.session.refresh(opportunity)
        return opportunity

    def test_catalog_includes_only_available_opportunities(self):
        available = self.create_database_opportunity()
        self.create_database_opportunity(status=OpportunityStatus.DRAFT)
        self.create_database_opportunity(status=OpportunityStatus.REJECTED)
        self.create_database_opportunity(
            committed_cents=10000,
        )
        self.create_database_opportunity(
            deadline=datetime.now(UTC) - timedelta(minutes=1),
        )
        self.create_database_opportunity(
            status=OpportunityStatus.CLOSED,
            date_closed=datetime.now(UTC),
        )

        response = self.client.get("/api/opportunities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [available.id])

    def test_empty_catalog_returns_empty_list(self):
        self.session.query(Opportunity).delete()
        self.session.commit()

        response = self.client.get("/api/opportunities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_unknown_opportunity_returns_not_found(self):
        response = self.client.get("/api/opportunities/999999")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
