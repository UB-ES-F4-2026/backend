"""Detall empresarial contra una base de dades aïllada i acabada de migrar."""
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.main import app
from app.models.business_opportunity import (
    BusinessOpportunity,
    BusinessPhase,
    BusinessSector,
)
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.user import User

DETAIL_KEYS = {
    "id",
    "type",
    "status",
    "title",
    "description",
    "location",
    "cover_image_url",
    "target_amount_cents",
    "committed_cents",
    "minimum_contribution_cents",
    "date_published",
    "deadline",
    "promoter",
    "business",
    "server_time",
}


class BusinessOpportunityDetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "business_detail_test_" + uuid4().hex
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
            user = User(email="business-promoter@example.com", hashed_password="x" * 60)
            db.add(user)
            db.flush()
            db.add(PromotingEntity(user_id=user.id, legal_name="Empresa SL"))
            db.commit()
            cls.promoter_id = user.id

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def create_business_opportunity(
        self,
        *,
        status=OpportunityStatus.PUBLISHED,
        deadline=None,
        committed_cents=10_000_000,
        with_business=True,
    ) -> int:
        opportunity = Opportunity(
            user_id=self.promoter_id,
            type=OpportunityType.EQUITY,
            status=status,
            title="Ronda de finançament",
            description="Descripció de l'oportunitat",
            location="Barcelona",
            cover_image_url="https://example.com/company.png",
            target_amount_cents=30_000_000,
            committed_cents=committed_cents,
            minimum_contribution_cents=100_00,
            deadline=deadline or datetime.now(UTC) + timedelta(days=30),
            date_published=datetime.now(UTC),
            date_closed=(
                datetime.now(UTC) if status == OpportunityStatus.CLOSED else None
            ),
        )
        if with_business:
            opportunity.business = BusinessOpportunity(
                sector=BusinessSector.FINTECH,
                phase=BusinessPhase.GROWTH,
                pre_investment_valuation_cents=270_000_000,
            )
        with self.Session() as db:
            db.add(opportunity)
            db.commit()
            return opportunity.id

    def test_business_detail_is_available_without_a_session(self):
        opportunity_id = self.create_business_opportunity()

        response = self.client.get(f"/api/opportunities/{opportunity_id}")
        self.assertEqual(response.status_code, 200, response.text)

    def test_returns_business_detail_and_calculates_equity_offered(self):
        opportunity_id = self.create_business_opportunity()
        before = datetime.now(UTC)

        response = self.client.get(
            f"/api/opportunities/{opportunity_id}"
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), DETAIL_KEYS)
        self.assertEqual(body["id"], opportunity_id)
        self.assertEqual(body["type"], "equity")
        self.assertEqual(body["title"], "Ronda de finançament")
        self.assertEqual(body["location"], "Barcelona")
        self.assertEqual(body["cover_image_url"], "https://example.com/company.png")
        self.assertEqual(body["target_amount_cents"], 30_000_000)
        self.assertEqual(body["committed_cents"], 10_000_000)
        self.assertEqual(body["minimum_contribution_cents"], 100_00)
        self.assertEqual(body["business"]["sector"], "fintech")
        self.assertEqual(body["business"]["phase"], "growth")
        self.assertEqual(body["business"]["pre_investment_valuation_cents"], 270_000_000)
        self.assertEqual(Decimal(body["business"]["equity_offered"]), Decimal("10"))
        self.assertEqual(body["promoter"]["legal_name"], "Empresa SL")
        self.assertIsNotNone(body["date_published"])
        self.assertGreater(
            datetime.fromisoformat(body["deadline"]),
            datetime.fromisoformat(body["date_published"]),
        )
        server_time = datetime.fromisoformat(body["server_time"])
        self.assertLessEqual(before, server_time)
        self.assertLessEqual(server_time, datetime.now(UTC))

    def test_funded_and_expired_business_details_remain_accessible(self):
        now = datetime.now(UTC)
        cases = {
            "funded": {"committed_cents": 30_000_000},
            "expired": {"deadline": now - timedelta(minutes=1)},
            "closed": {"status": OpportunityStatus.CLOSED},
        }
        for name, changes in cases.items():
            with self.subTest(name):
                opportunity_id = self.create_business_opportunity(**changes)
                response = self.client.get(
                    f"/api/opportunities/{opportunity_id}"
                )
                self.assertEqual(response.status_code, 200, response.text)

    def test_equity_parent_without_business_data_returns_not_found(self):
        opportunity_id = self.create_business_opportunity(with_business=False)

        response = self.client.get(
            f"/api/opportunities/{opportunity_id}"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Oportunidad no disponible"})

    def test_pre_investment_valuation_must_be_positive(self):
        with self.Session() as db:
            opportunity = Opportunity(
                user_id=self.promoter_id,
                type=OpportunityType.EQUITY,
                title="Empresa",
                description="Descripció",
                location="Barcelona",
                target_amount_cents=10_000,
                deadline=datetime.now(UTC) + timedelta(days=1),
                date_published=datetime.now(UTC),
            )
            opportunity.business = BusinessOpportunity(
                sector=BusinessSector.OTHER,
                phase=BusinessPhase.PRE_SEED,
                pre_investment_valuation_cents=0,
            )
            db.add(opportunity)
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_business_table_has_type_specific_fields(self):
        columns = {
            column["name"]
            for column in inspect(self.isolated).get_columns("business_opportunities")
        }
        self.assertEqual(
            columns,
            {
                "opportunity_id",
                "sector",
                "phase",
                "pre_investment_valuation_cents",
            },
        )
        with self.isolated.connect() as connection:
            sectors = connection.scalars(
                text("SELECT unnest(enum_range(NULL::business_sector))::text")
            ).all()
            phases = connection.scalars(
                text("SELECT unnest(enum_range(NULL::business_phase))::text")
            ).all()
        self.assertEqual(
            sectors,
            [
                "fintech",
                "industry",
                "saas",
                "health",
                "biotech",
                "cleantech",
                "agritech",
                "foodtech",
                "d2c",
                "education",
                "media",
                "tourism",
                "logistic",
                "ai",
                "other",
            ],
        )
        self.assertEqual(phases, ["pre_seed", "seed", "early", "growth", "late"])

    def test_sector_migration_preserves_and_maps_existing_values(self):
        database = "business_sector_migration_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        isolated = create_engine(engine.url.set(database=database))
        config = Config("/app/alembic.ini")

        def migrate(operation, revision):
            with isolated.begin() as connection:
                config.attributes["connection"] = connection
                operation(config, revision)

        try:
            migrate(command.upgrade, "0f4afe25bff8")
            with isolated.begin() as connection:
                user_id = connection.scalar(
                    text(
                        "INSERT INTO users (email, hashed_password) "
                        "VALUES ('sector-migration@example.com', :password) "
                        "RETURNING id"
                    ),
                    {"password": "x" * 60},
                )
                connection.execute(
                    text(
                        "INSERT INTO promoting_entities (user_id, legal_name) "
                        "VALUES (:user_id, 'Migració SL')"
                    ),
                    {"user_id": user_id},
                )
                for index, sector in enumerate(("healthtech", "edtech", "fintech")):
                    opportunity_id = connection.scalar(
                        text(
                            """
                            INSERT INTO opportunities (
                                user_id, type, status, title, description, location,
                                target_amount_cents, deadline, date_published
                            )
                            VALUES (
                                :user_id, 'equity', 'published', :title, 'Descripció',
                                'Barcelona', 10000, now() + interval '1 day', now()
                            )
                            RETURNING id
                            """
                        ),
                        {"user_id": user_id, "title": f"Empresa {index}"},
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO business_opportunities (
                                opportunity_id, sector, phase,
                                pre_investment_valuation_cents
                            )
                            VALUES (
                                :opportunity_id, CAST(:sector AS business_sector),
                                'seed', 20000
                            )
                            """
                        ),
                        {"opportunity_id": opportunity_id, "sector": sector},
                    )

            migrate(command.upgrade, "head")
            with isolated.connect() as connection:
                upgraded_sectors = connection.scalars(
                    text(
                        "SELECT sector::text FROM business_opportunities "
                        "ORDER BY opportunity_id"
                    )
                ).all()
            self.assertEqual(upgraded_sectors, ["health", "education", "fintech"])

            migrate(command.downgrade, "0f4afe25bff8")
            with isolated.connect() as connection:
                downgraded_sectors = connection.scalars(
                    text(
                        "SELECT sector::text FROM business_opportunities "
                        "ORDER BY opportunity_id"
                    )
                ).all()
            self.assertEqual(
                downgraded_sectors,
                ["healthtech", "edtech", "fintech"],
            )
        finally:
            isolated.dispose()
            with engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))


if __name__ == "__main__":
    unittest.main()
