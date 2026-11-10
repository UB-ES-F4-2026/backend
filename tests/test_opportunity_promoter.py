"""Toda oportunidad pertenece a una entidad promotora."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models.opportunity import Opportunity, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.user import User


class IsolatedDatabase:
    """Base de datos temporal migrada hasta la revisión indicada."""

    def __init__(self, prefix: str, revision: str):
        self.name = prefix + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{self.name}"'))
        self.engine = create_engine(engine.url.set(database=self.name))
        self.migrate(revision)

    def migrate(self, revision: str) -> None:
        config = Config("/app/alembic.ini")
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)

    def drop(self) -> None:
        self.engine.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{self.name}" WITH (FORCE)'))


class OpportunityPromoterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = IsolatedDatabase("opportunity_promoter_test_", "head")
        cls.Session = sessionmaker(
            bind=cls.database.engine, autoflush=False, expire_on_commit=False
        )

    @classmethod
    def tearDownClass(cls):
        cls.database.drop()

    def new_user(self, db, with_promoter: bool) -> int:
        user = User(email=f"{uuid4().hex}@example.com", hashed_password="x" * 60)
        db.add(user)
        db.flush()
        if with_promoter:
            db.add(PromotingEntity(user_id=user.id, legal_name="Promotora SL"))
        db.commit()
        return user.id

    def new_opportunity(self, user_id) -> Opportunity:
        return Opportunity(
            user_id=user_id,
            type=OpportunityType.REAL_ESTATE,
            title="Edificio",
            description="Descripción",
            location="Girona, Girona, España",
            target_amount_cents=100_000_00,
            deadline=datetime.now(UTC) + timedelta(days=30),
            date_published=datetime.now(UTC),
        )

    def test_opportunity_loads_its_promoter(self):
        with self.Session() as db:
            user_id = self.new_user(db, with_promoter=True)
            opportunity = self.new_opportunity(user_id)
            db.add(opportunity)
            db.commit()
            self.assertEqual(opportunity.promoter.legal_name, "Promotora SL")

    def test_user_without_promoting_entity_cannot_own_opportunities(self):
        with self.Session() as db:
            user_id = self.new_user(db, with_promoter=False)
            db.add(self.new_opportunity(user_id))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_opportunity_requires_an_owner(self):
        with self.Session() as db:
            db.add(self.new_opportunity(None))
            with self.assertRaises(IntegrityError):
                db.commit()


class PromoterMigrationTest(unittest.TestCase):
    """La migración 0010 elimina las oportunidades sin entidad promotora."""

    def setUp(self):
        self.database = IsolatedDatabase("promoter_migration_test_", "0009")

    def tearDown(self):
        self.database.drop()

    def insert_opportunity(self, connection, user_id) -> int:
        return connection.execute(
            text(
                """
                INSERT INTO opportunities (user_id, type, title, description, location,
                    target_amount_cents, committed_cents, deadline, date_published)
                VALUES (:user_id, 'real_estate', 'Edificio', 'Descripción', 'Girona',
                    100000, 0, now() + interval '30 days', now())
                RETURNING id
                """
            ),
            {"user_id": user_id},
        ).scalar_one()

    def insert_user(self, connection, with_promoter: bool) -> int:
        user_id = connection.execute(
            text(
                "INSERT INTO users (email, hashed_password) VALUES (:email, :password) "
                "RETURNING id"
            ),
            {"email": f"{uuid4().hex}@example.com", "password": "x" * 60},
        ).scalar_one()
        if with_promoter:
            connection.execute(
                text(
                    "INSERT INTO promoting_entities (user_id, legal_name) "
                    "VALUES (:user_id, 'Promotora SL')"
                ),
                {"user_id": user_id},
            )
        return user_id

    def test_orphan_opportunities_are_deleted_and_the_rest_kept(self):
        with self.database.engine.begin() as connection:
            kept = self.insert_opportunity(
                connection, self.insert_user(connection, with_promoter=True)
            )
            without_promoter = self.insert_opportunity(
                connection, self.insert_user(connection, with_promoter=False)
            )
            without_owner = self.insert_opportunity(connection, None)
            connection.execute(
                text(
                    "INSERT INTO real_estate_opportunities (opportunity_id, purpose, "
                    "intended_use, asset_type, surface_m2) "
                    "VALUES (:id, 'acquisition', 'sale', 'commercial', 100)"
                ),
                {"id": without_promoter},
            )

        self.database.migrate("head")

        with self.database.engine.connect() as connection:
            remaining = connection.scalars(text("SELECT id FROM opportunities")).all()
            real_estate = connection.scalars(
                text("SELECT opportunity_id FROM real_estate_opportunities")
            ).all()
        self.assertEqual(remaining, [kept])
        self.assertNotIn(without_owner, remaining)
        self.assertEqual(real_estate, [])


if __name__ == "__main__":
    unittest.main()
