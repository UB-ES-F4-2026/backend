"""Imports de les oportunitats per sobre del que cap en un enter de 32 bits."""
import json
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.core import media
from app.core.commitments import reserve_funds
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
from app.models.wallet import Wallet
from app.schemas.wallet import MAX_SAFE_CENTS

# El màxim d'un INTEGER de PostgreSQL: 21.474.836,47 € en cèntims.
MAX_INT32 = 2**31 - 1
PREVIOUS_REVISION = "c4f8a1d2e6b3"
AMOUNT_COLUMNS = {
    "opportunities": (
        "target_amount_cents",
        "committed_cents",
        "minimum_contribution_cents",
    ),
    "business_opportunities": ("pre_investment_valuation_cents",),
}


def column_types(isolated) -> dict[str, str]:
    inspector = inspect(isolated)
    return {
        f"{table}.{column['name']}": str(column["type"])
        for table, names in AMOUNT_COLUMNS.items()
        for column in inspector.get_columns(table)
        if column["name"] in names
    }


class LargeOpportunityAmountsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = TemporaryDirectory()
        cls.previous_media_root = media.MEDIA_ROOT
        media.MEDIA_ROOT = Path(cls.media_directory.name)
        cls.database = "opportunity_amounts_test_" + uuid4().hex
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

        with cls.Session() as db:
            cls.user = User(
                email="promoter@example.com",
                hashed_password="x" * 60,
                wallet=Wallet(available_cents=0),
            )
            db.add(cls.user)
            db.flush()
            db.add(PromotingEntity(user_id=cls.user.id, legal_name="Promociones Girona SL"))
            db.commit()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: cls.user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))
        media.MEDIA_ROOT = cls.previous_media_root
        cls.media_directory.cleanup()

    def set_wallet_balance(self, available_cents: int) -> None:
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
            wallet.available_cents = available_cents
            wallet.committed_cents = 0
            db.commit()

    def balances(self) -> tuple[int, int]:
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user.id))
            return wallet.available_cents, wallet.committed_cents

    def opportunity(self, opportunity_id: int) -> Opportunity:
        with self.Session() as db:
            opportunity = db.get(Opportunity, opportunity_id)
            # Carrega les dades empresarials abans de tancar la sessió.
            _ = opportunity.business
            return opportunity

    def opportunity_count(self) -> int:
        with self.Session() as db:
            return db.scalar(select(func.count()).select_from(Opportunity))

    def real_estate_body(self, **changes) -> dict:
        body = {
            "type": "real_estate",
            "title": "Promoció residencial",
            "description": "Descripció.",
            "location": {
                "municipality": "Barcelona",
                "province": "Barcelona",
                "country": "Spain",
            },
            "target_amount_cents": 50_000_000_00,
            "minimum_contribution_cents": 50_00,
            "deadline": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "real_estate": {
                "purpose": "acquisition",
                "intended_use": "rental",
                "asset_type": "residential",
                "surface_m2": "250.50",
                "planned_housing_units": 4,
            },
        }
        body.update(changes)
        return body

    def business_body(self, **changes) -> dict:
        body = self.real_estate_body(type="equity", real_estate=None)
        body["business"] = {
            "sector": "technology",
            "phase": "growth",
            "pre_investment_valuation_cents": 450_000_000_00,
        }
        body.update(changes)
        return body

    def post_opportunity(self, body: dict):
        files = [
            ("metadata", (None, json.dumps(body))),
            ("images", ("image.png", b"\x89PNG\r\n\x1a\nimage", "image/png")),
        ]
        return self.client.post("/api/opportunities", files=files)

    def publish(self, opportunity_id: int) -> None:
        with self.Session() as db:
            opportunity = db.get(Opportunity, opportunity_id)
            opportunity.status = OpportunityStatus.PUBLISHED
            opportunity.date_published = datetime.now(UTC)
            db.commit()

    def test_target_and_minimum_beyond_32_bits_are_stored_exactly(self):
        # Objectiu de 50.000.000,00 € i mínim de 25.000.000,00 €.
        response = self.post_opportunity(
            self.real_estate_body(minimum_contribution_cents=25_000_000_00)
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["target_amount_cents"], 50_000_000_00)
        stored = self.opportunity(response.json()["id"])
        self.assertGreater(stored.target_amount_cents, MAX_INT32)
        self.assertEqual(stored.target_amount_cents, 50_000_000_00)
        self.assertEqual(stored.minimum_contribution_cents, 25_000_000_00)

    def test_initial_contribution_beyond_32_bits_is_reserved(self):
        self.set_wallet_balance(40_000_000_00)

        response = self.post_opportunity(
            self.real_estate_body(initial_contribution_cents=30_000_000_00)
        )

        self.assertEqual(response.status_code, 201, response.text)
        stored = self.opportunity(response.json()["id"])
        self.assertEqual(stored.committed_cents, 30_000_000_00)
        self.assertEqual(self.balances(), (10_000_000_00, 30_000_000_00))

    def test_valuation_beyond_32_bits_is_stored_and_used_for_the_equity_offered(self):
        # Valoració prèvia de 450.000.000 € i objectiu de 50.000.000 €: s'ofereix un 10 %.
        response = self.post_opportunity(self.business_body())

        self.assertEqual(response.status_code, 201, response.text)
        opportunity_id = response.json()["id"]
        stored = self.opportunity(opportunity_id)
        self.assertEqual(stored.business.pre_investment_valuation_cents, 450_000_000_00)

        self.publish(opportunity_id)
        detail = self.client.get(f"/api/opportunities/{opportunity_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(body["target_amount_cents"], 50_000_000_00)
        self.assertEqual(body["business"]["pre_investment_valuation_cents"], 450_000_000_00)
        self.assertEqual(Decimal(body["business"]["equity_offered"]), Decimal("10"))

    def test_published_opportunity_beyond_32_bits_is_listed_in_the_catalog(self):
        response = self.post_opportunity(self.real_estate_body())
        opportunity_id = response.json()["id"]
        self.publish(opportunity_id)

        catalog = self.client.get("/api/opportunities")

        self.assertEqual(catalog.status_code, 200, catalog.text)
        listed = {item["id"]: item for item in catalog.json()}
        self.assertEqual(listed[opportunity_id]["target_amount_cents"], 50_000_000_00)

    def test_largest_safe_amount_is_accepted(self):
        response = self.post_opportunity(
            self.business_body(
                target_amount_cents=MAX_SAFE_CENTS,
                business={
                    "sector": "technology",
                    "phase": "growth",
                    "pre_investment_valuation_cents": MAX_SAFE_CENTS,
                },
            )
        )

        self.assertEqual(response.status_code, 201, response.text)
        stored = self.opportunity(response.json()["id"])
        self.assertEqual(stored.target_amount_cents, MAX_SAFE_CENTS)
        self.assertEqual(stored.business.pre_investment_valuation_cents, MAX_SAFE_CENTS)

    def test_amounts_above_the_largest_safe_integer_are_rejected(self):
        too_large = MAX_SAFE_CENTS + 1
        self.set_wallet_balance(MAX_SAFE_CENTS)
        bodies = {
            "target_amount_cents": self.real_estate_body(target_amount_cents=too_large),
            "minimum_contribution_cents": self.real_estate_body(
                target_amount_cents=MAX_SAFE_CENTS, minimum_contribution_cents=too_large
            ),
            "initial_contribution_cents": self.real_estate_body(
                target_amount_cents=MAX_SAFE_CENTS, initial_contribution_cents=too_large
            ),
            "pre_investment_valuation_cents": self.business_body(
                business={
                    "sector": "technology",
                    "phase": "growth",
                    "pre_investment_valuation_cents": too_large,
                }
            ),
        }
        before = self.opportunity_count()

        for field, body in bodies.items():
            with self.subTest(field=field):
                response = self.post_opportunity(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn(field, json.dumps(response.json()["detail"]))

        self.assertEqual(self.opportunity_count(), before)
        self.assertEqual(self.balances(), (MAX_SAFE_CENTS, 0))

    def test_committed_capital_can_grow_past_32_bits(self):
        # El capital compromès travessa el límit antic amb una sola aportació.
        self.set_wallet_balance(1_000_00)
        with self.Session() as db:
            opportunity = Opportunity(
                user_id=self.user.id,
                type=OpportunityType.REAL_ESTATE,
                status=OpportunityStatus.PUBLISHED,
                title="Promoció residencial",
                description="Descripció.",
                location="Barcelona",
                target_amount_cents=50_000_000_00,
                committed_cents=MAX_INT32 - 50_00,
                minimum_contribution_cents=50_00,
                deadline=datetime.now(UTC) + timedelta(days=30),
                date_published=datetime.now(UTC),
            )
            db.add(opportunity)
            db.commit()
            opportunity_id = opportunity.id

        with self.Session() as db:
            reserve_funds(
                db, user_id=self.user.id, opportunity_id=opportunity_id, amount_cents=100_00
            )
            db.commit()

        stored = self.opportunity(opportunity_id)
        self.assertEqual(stored.committed_cents, MAX_INT32 + 50_00)
        self.assertEqual(self.balances(), (900_00, 100_00))


class OpportunityAmountsMigrationTest(unittest.TestCase):
    def test_existing_amounts_are_kept_and_columns_become_64_bit(self):
        database = "opportunity_amounts_migration_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        isolated = create_engine(engine.url.set(database=database))
        Session = sessionmaker(bind=isolated, autoflush=False, expire_on_commit=False)
        config = Config("/app/alembic.ini")

        def migrate(operation, revision: str) -> None:
            with isolated.begin() as connection:
                config.attributes["connection"] = connection
                operation(config, revision)

        def amounts(opportunity_id: int) -> tuple:
            with isolated.connect() as connection:
                return tuple(
                    connection.execute(
                        text(
                            "SELECT o.target_amount_cents, o.committed_cents, "
                            "o.minimum_contribution_cents, b.pre_investment_valuation_cents "
                            "FROM opportunities o JOIN business_opportunities b "
                            "ON b.opportunity_id = o.id WHERE o.id = :id"
                        ),
                        {"id": opportunity_id},
                    ).one()
                )

        def set_target(opportunity_id: int, target_amount_cents: int) -> None:
            with isolated.begin() as connection:
                connection.execute(
                    text("UPDATE opportunities SET target_amount_cents = :t WHERE id = :id"),
                    {"t": target_amount_cents, "id": opportunity_id},
                )

        try:
            migrate(command.upgrade, PREVIOUS_REVISION)
            self.assertEqual(set(column_types(isolated).values()), {"INTEGER"})
            # Dades anteriors a la migració, amb els valors més grans que hi cabien.
            with Session() as db:
                user = User(email="promoter@example.com", hashed_password="x" * 60)
                db.add(user)
                db.flush()
                db.add(PromotingEntity(user_id=user.id, legal_name="Empresa SL"))
                opportunity = Opportunity(
                    user_id=user.id,
                    type=OpportunityType.EQUITY,
                    status=OpportunityStatus.PUBLISHED,
                    title="Ronda de finançament",
                    description="Descripció.",
                    location="Barcelona",
                    target_amount_cents=MAX_INT32,
                    committed_cents=2_000_000_000,
                    minimum_contribution_cents=100_00,
                    deadline=datetime.now(UTC) + timedelta(days=30),
                    date_published=datetime.now(UTC),
                    business=BusinessOpportunity(
                        sector=BusinessSector.TECHNOLOGY,
                        phase=BusinessPhase.GROWTH,
                        pre_investment_valuation_cents=MAX_INT32,
                    ),
                )
                db.add(opportunity)
                db.commit()
                opportunity_id = opportunity.id
            before = amounts(opportunity_id)
            self.assertEqual(before, (MAX_INT32, 2_000_000_000, 100_00, MAX_INT32))
            with self.assertRaises(DBAPIError):
                set_target(opportunity_id, MAX_INT32 + 1)

            migrate(command.upgrade, "head")
            self.assertEqual(set(column_types(isolated).values()), {"BIGINT"})
            self.assertEqual(len(column_types(isolated)), 4)
            self.assertEqual(amounts(opportunity_id), before)
            set_target(opportunity_id, 50_000_000_00)
            self.assertEqual(amounts(opportunity_id)[0], 50_000_000_00)

            # Amb un import que ja no cap en 32 bits, desfer la migració falla sencera.
            with self.assertRaises(DBAPIError):
                migrate(command.downgrade, PREVIOUS_REVISION)
            self.assertEqual(set(column_types(isolated).values()), {"BIGINT"})
            self.assertEqual(amounts(opportunity_id)[0], 50_000_000_00)

            set_target(opportunity_id, MAX_INT32)
            migrate(command.downgrade, PREVIOUS_REVISION)
            self.assertEqual(set(column_types(isolated).values()), {"INTEGER"})
            self.assertEqual(amounts(opportunity_id), before)
        finally:
            isolated.dispose()
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))


if __name__ == "__main__":
    unittest.main()
