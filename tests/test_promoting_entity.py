"""Entidades promotoras contra una base de datos aislada y recién migrada."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.main import app
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.user import User

URL = "/api/promotingentity"


class PromotingEntityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "promoting_entity_test_" + uuid4().hex
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

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def setUp(self):
        # HTTPS: el cliente solo reenvía cookies Secure por HTTPS.
        self.client = TestClient(app, base_url="https://testserver")

    def log_in_new_user(self) -> int:
        email = f"{uuid4().hex}@example.com"
        credentials = {"email": email, "password": "correct-horse"}
        user_id = self.client.post("/api/auth/register", json=credentials).json()["id"]
        self.assertEqual(self.client.post("/api/auth/login", json=credentials).status_code, 200)
        return user_id

    def add_opportunity(self, user_id, status, published):
        with self.Session() as db:
            db.add(Opportunity(
                user_id=user_id,
                type=OpportunityType.REAL_ESTATE,
                status=status,
                title="Proyecto",
                description="Descripción",
                location="Barcelona, Barcelona, España",
                target_amount_cents=100_000_00,
                deadline=datetime.now(UTC) + timedelta(days=30),
                date_published=datetime.now(UTC) if published else None,
            ))
            db.commit()

    def entity_in_list(self, user_id):
        response = TestClient(app, base_url="https://testserver").get(URL)
        self.assertEqual(response.status_code, 200)
        return next(entity for entity in response.json() if entity["user_id"] == user_id)

    def test_create_requires_session(self):
        response = self.client.post(URL, json={"legal_name": "Promociones SL"})
        self.assertEqual(response.status_code, 401)

    def test_logged_in_user_creates_associated_entity(self):
        user_id = self.log_in_new_user()
        body = {
            "legal_name": "  Promociones SL  ",
            "image_url": "https://example.com/logo.png",
            "experience_years": 12,
            "location": "Girona, Girona, España",
        }
        response = self.client.post(URL, json=body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {
            "user_id": user_id,
            "legal_name": "Promociones SL",
            "image_url": "https://example.com/logo.png",
            "published_projects_count": 0,
            "experience_years": 12,
            "location": "Girona, Girona, España",
        })

    def test_optional_fields_can_be_omitted(self):
        self.log_in_new_user()
        response = self.client.post(URL, json={"legal_name": "Solo Nombre SL"})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsNone(body["image_url"])
        self.assertIsNone(body["experience_years"])
        self.assertIsNone(body["location"])

    def test_user_cannot_create_a_second_entity(self):
        self.log_in_new_user()
        self.assertEqual(self.client.post(URL, json={"legal_name": "Primera SL"}).status_code, 201)
        response = self.client.post(URL, json={"legal_name": "Segunda SL"})
        self.assertEqual(response.status_code, 409)

    def test_invalid_data_is_rejected(self):
        self.log_in_new_user()
        self.assertEqual(self.client.post(URL, json={}).status_code, 422)
        self.assertEqual(self.client.post(URL, json={"legal_name": "   "}).status_code, 422)
        response = self.client.post(URL, json={"legal_name": "X SL", "experience_years": -1})
        self.assertEqual(response.status_code, 422)

    def test_list_is_public_and_counts_only_published_projects(self):
        user_id = self.log_in_new_user()
        self.client.post(URL, json={"legal_name": "Contadora SL"})
        other_user_id = self.log_in_new_user()

        self.add_opportunity(user_id, OpportunityStatus.PUBLISHED, published=True)
        self.add_opportunity(user_id, OpportunityStatus.CLOSED, published=True)
        self.add_opportunity(user_id, OpportunityStatus.DRAFT, published=False)
        self.add_opportunity(user_id, OpportunityStatus.REJECTED, published=False)
        self.add_opportunity(other_user_id, OpportunityStatus.PUBLISHED, published=True)

        self.assertEqual(self.entity_in_list(user_id)["published_projects_count"], 2)

    def test_list_does_not_expose_private_user_data(self):
        user_id = self.log_in_new_user()
        self.client.post(URL, json={"legal_name": "Privada SL"})
        entity = self.entity_in_list(user_id)
        self.assertNotIn("email", entity)
        self.assertNotIn("hashed_password", entity)

    def test_entity_is_deleted_with_its_user(self):
        user_id = self.log_in_new_user()
        self.client.post(URL, json={"legal_name": "Efímera SL"})
        with self.Session() as db:
            db.delete(db.get(User, user_id))
            db.commit()
            self.assertIsNone(db.scalar(
                select(PromotingEntity).where(PromotingEntity.user_id == user_id)
            ))


if __name__ == "__main__":
    unittest.main()
