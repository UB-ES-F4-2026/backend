"""Create and read investment opportunities through the API."""
import json
import unittest
from datetime import UTC, datetime, timedelta
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
from app.models.commitment import Commitment
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.opportunity_image import OpportunityImage
from app.models.promoting_entity import PromotingEntity
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
        self.assertEqual(len(body["images"]), 1)
        self.assertEqual(body["cover_image_url"], body["images"][0]["url"])
        image = self.session.scalar(
            select(OpportunityImage).where(OpportunityImage.opportunity_id == body["id"])
        )
        self.assertEqual(image.position, 0)
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

    def test_get_opportunity_hides_non_real_estate_opportunities(self):
        # US02.2.1: el detalle solo muestra oportunidades inmobiliarias.
        created = self.post_opportunity(self.opportunity_body(type="equity"))
        opportunity_id = created.json()["id"]

        response = self.client.get(f"/api/opportunities/{opportunity_id}")

        self.assertEqual(response.status_code, 404)

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
