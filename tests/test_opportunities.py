"""Create and read investment opportunities through the API."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database import engine, get_db
from app.main import app
from app.models.user import User


class OpportunitiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def opportunity_body(self, **changes):
        body = {
            "type": "real_estate",
            "title": "Investment opportunity",
            "description": "A test opportunity",
            "location": "Barcelona",
            "cover_image_url": None,
            "target_amount_cents": 25000000,
            "committed_cents": 10000,
            "deadline": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        }
        body.update(changes)
        return body

    def test_create_opportunity_requires_authentication(self):
        app.dependency_overrides.pop(get_current_user)
        response = self.client.post(
            "/api/opportunities",
            json=self.opportunity_body(),
        )
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.assertEqual(response.status_code, 401)

    def test_create_opportunity_assigns_current_user(self):
        response = self.client.post(
            "/api/opportunities",
            json=self.opportunity_body(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["user_id"], self.user.id)
        self.assertEqual(body["committed_cents"], 10000)
        self.assertEqual(body["type"], "real_estate")

    def test_create_opportunity_rejects_invalid_data(self):
        response = self.client.post(
            "/api/opportunities",
            json=self.opportunity_body(
                type="invalid",
                target_amount_cents=0,
            ),
        )

        self.assertEqual(response.status_code, 422)

    def test_get_opportunity_returns_created_opportunity(self):
        created = self.client.post(
            "/api/opportunities",
            json=self.opportunity_body(type="equity"),
        )
        opportunity_id = created.json()["id"]

        response = self.client.get(f"/api/opportunities/{opportunity_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], opportunity_id)
        self.assertEqual(response.json()["type"], "equity")

    def test_get_unknown_opportunity_returns_not_found(self):
        response = self.client.get("/api/opportunities/999999")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
