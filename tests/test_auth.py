"""Register and login against an isolated, freshly migrated database."""
import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.main import app


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "auth_test_" + uuid4().hex
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

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def register(self, email, password="correct-horse"):
        return self.client.post("/api/auth/register", json={"email": email, "password": password})

    def login(self, email, password="correct-horse"):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def test_register_login_and_me(self):
        response = self.register("Ana@Example.com")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["email"], "ana@example.com")
        self.assertNotIn("password", body)
        self.assertNotIn("hashed_password", body)

        response = self.login("ana@example.com")
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]

        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "ana@example.com")

    def test_duplicate_email_is_rejected(self):
        self.assertEqual(self.register("dup@example.com").status_code, 201)
        self.assertEqual(self.register("DUP@example.com").status_code, 409)

    def test_invalid_registration_data(self):
        self.assertEqual(self.register("not-an-email").status_code, 422)
        self.assertEqual(self.register("short@example.com", "1234567").status_code, 422)

    def test_wrong_password_and_unknown_email(self):
        self.register("bob@example.com")
        self.assertEqual(self.login("bob@example.com", "wrong-password").status_code, 401)
        self.assertEqual(self.login("nobody@example.com").status_code, 401)

    def test_me_requires_valid_token(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        response = self.client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
