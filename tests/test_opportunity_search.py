"""Búsqueda por título en el catálogo: GET /api/opportunities?name=..."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.main import app
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.user import User

URL = "/api/opportunities"


class OpportunitySearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "opportunity_search_test_" + uuid4().hex
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

        with cls.Session() as db:
            user = User(email="search@example.com", hashed_password="x" * 60)
            db.add(user)
            db.flush()
            db.add(PromotingEntity(user_id=user.id, legal_name="Buscadora SL"))
            db.commit()
            cls.promoter_id = user.id

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def setUp(self):
        with self.Session() as db:
            db.execute(delete(Opportunity))
            db.commit()

    def add(self, title: str, **changes) -> int:
        values = {
            "user_id": self.promoter_id,
            "type": OpportunityType.REAL_ESTATE,
            "status": OpportunityStatus.PUBLISHED,
            "title": title,
            "description": "Descripción",
            "location": "Girona, Girona, España",
            "target_amount_cents": 100_000_00,
            "deadline": datetime.now(UTC) + timedelta(days=30),
            "date_published": datetime.now(UTC),
        }
        values.update(changes)
        with self.Session() as db:
            opportunity = Opportunity(**values)
            db.add(opportunity)
            db.commit()
            return opportunity.id

    def search(self, name: str | None) -> list[str]:
        params = {} if name is None else {"name": name}
        response = self.client.get(URL, params=params)
        self.assertEqual(response.status_code, 200)
        return [opportunity["title"] for opportunity in response.json()]

    def test_without_name_returns_the_whole_catalog(self):
        self.add("Piso en Girona")
        self.add("Nave en Reus")
        self.assertEqual(sorted(self.search(None)), ["Nave en Reus", "Piso en Girona"])
        self.assertEqual(sorted(self.search("   ")), ["Nave en Reus", "Piso en Girona"])

    def test_exact_match_ignores_case_and_accents(self):
        self.add("Rehabilitación de edificio en Lleida")
        self.add("Nave en Reus")
        self.assertEqual(self.search("REHABILITACION"), ["Rehabilitación de edificio en Lleida"])
        self.assertEqual(self.search("lléida"), ["Rehabilitación de edificio en Lleida"])

    def test_exact_matches_exclude_approximate_ones(self):
        self.add("Piso en Girona")
        self.add("Piso en Gerona")
        self.assertEqual(self.search("girona"), ["Piso en Girona"])

    def test_sql_wildcards_have_no_special_meaning(self):
        self.add("Piso en Girona")
        self.add("Descuento 100% garantizado")
        # La puntuación se ignora: "100%" busca "100" y "_" no actúa como comodín.
        self.assertEqual(self.search("100%"), ["Descuento 100% garantizado"])
        self.assertEqual(self.search("piso_en"), ["Piso en Girona"])
        # Solo puntuación equivale a no buscar nada: catálogo completo.
        self.assertEqual(len(self.search("%")), 2)

    def test_typos_are_found_ordered_by_distance(self):
        self.add("Casa en Gerona")
        self.add("Casa en Girona")
        self.assertEqual(self.search("girnoa"), ["Casa en Girona", "Casa en Gerona"])

    def test_no_results_beyond_distance_three(self):
        self.add("Piso en Girona")
        self.assertEqual(self.search("Gwxyza"), [])

    def test_only_available_opportunities_are_searched(self):
        self.add("Piso en Girona")
        self.add("Piso en Girona cerrado", status=OpportunityStatus.CLOSED,
                 date_closed=datetime.now(UTC))
        self.add("Piso en Girona borrador", status=OpportunityStatus.DRAFT, date_published=None)
        self.add("Piso en Girona vencido", deadline=datetime.now(UTC) - timedelta(minutes=1))
        self.assertEqual(self.search("girona"), ["Piso en Girona"])

    def test_name_longer_than_255_characters_is_rejected(self):
        response = self.client.get(URL, params={"name": "a" * 256})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
