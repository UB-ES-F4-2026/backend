"""Modelo padre + categoría inmobiliaria contra una base de datos aislada y recién migrada."""
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.real_estate_opportunity import (
    AssetType,
    IntendedUse,
    RealEstateOpportunity,
    RealEstatePurpose,
)
from app.models.user import User


class RealEstateOpportunitiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "real_estate_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        cls.isolated = create_engine(engine.url.set(database=cls.database))
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        cls.Session = sessionmaker(bind=cls.isolated, autoflush=False, expire_on_commit=False)
        # Toda oportunidad necesita una entidad promotora.
        with cls.Session() as db:
            user = User(email="promoter@example.com", hashed_password="x" * 60)
            db.add(user)
            db.flush()
            db.add(PromotingEntity(user_id=user.id, legal_name="Promotora SL"))
            db.commit()
            cls.promoter_id = user.id

    @classmethod
    def tearDownClass(cls):
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def new_opportunity(self, **changes) -> Opportunity:
        values = {
            "user_id": self.promoter_id,
            "type": OpportunityType.REAL_ESTATE,
            "title": "Edificio",
            "description": "Descripción",
            "location": "Girona, Girona, España",
            "target_amount_cents": 100_000_00,
            "deadline": datetime.now(UTC) + timedelta(days=30),
            "date_published": datetime.now(UTC),
        }
        values.update(changes)
        return Opportunity(**values)

    def real_estate(self, **changes) -> RealEstateOpportunity:
        values = {
            "purpose": RealEstatePurpose.CONSTRUCTION,
            "intended_use": IntendedUse.RENTAL,
            "asset_type": AssetType.COMMERCIAL,
            "surface_m2": Decimal("250.50"),
        }
        values.update(changes)
        return RealEstateOpportunity(**values)

    def save_with_real_estate(self, **changes) -> int:
        with self.Session() as db:
            opportunity = self.new_opportunity()
            opportunity.real_estate = self.real_estate(**changes)
            db.add(opportunity)
            db.commit()
            return opportunity.id

    def test_schema_has_new_column_and_table(self):
        inspector = inspect(self.isolated)
        opportunity_columns = {c["name"] for c in inspector.get_columns("opportunities")}
        self.assertIn("minimum_contribution_cents", opportunity_columns)
        real_estate_columns = {c["name"] for c in inspector.get_columns("real_estate_opportunities")}
        self.assertEqual(real_estate_columns, {
            "opportunity_id", "purpose", "intended_use", "asset_type", "surface_m2",
            "planned_housing_units", "estimated_works_end", "estimated_rental_start",
            "public_latitude", "public_longitude",
        })
        self.assertEqual(
            inspector.get_pk_constraint("real_estate_opportunities")["constrained_columns"],
            ["opportunity_id"],
        )

    def test_full_record_round_trip(self):
        opportunity_id = self.save_with_real_estate(
            purpose=RealEstatePurpose.ACQUISITION_AND_RENOVATION,
            asset_type=AssetType.RESIDENTIAL,
            planned_housing_units=12,
            estimated_works_end=date(2027, 6, 30),
            estimated_rental_start=date(2027, 9, 1),
            public_latitude=Decimal("41.981800"),
            public_longitude=Decimal("2.823700"),
        )
        with self.Session() as db:
            opportunity = db.get(Opportunity, opportunity_id)
            real_estate = opportunity.real_estate
            self.assertEqual(real_estate.opportunity_id, opportunity_id)
            self.assertEqual(real_estate.purpose, RealEstatePurpose.ACQUISITION_AND_RENOVATION)
            self.assertEqual(real_estate.intended_use, IntendedUse.RENTAL)
            self.assertEqual(real_estate.asset_type, AssetType.RESIDENTIAL)
            self.assertEqual(real_estate.surface_m2, Decimal("250.50"))
            self.assertEqual(real_estate.planned_housing_units, 12)
            self.assertEqual(real_estate.estimated_works_end, date(2027, 6, 30))
            self.assertEqual(real_estate.estimated_rental_start, date(2027, 9, 1))
            self.assertEqual(real_estate.public_latitude, Decimal("41.981800"))
            self.assertEqual(real_estate.public_longitude, Decimal("2.823700"))

    def test_optional_fields_can_be_null(self):
        opportunity_id = self.save_with_real_estate(
            purpose=RealEstatePurpose.ACQUISITION, intended_use=IntendedUse.SALE
        )
        with self.Session() as db:
            real_estate = db.get(RealEstateOpportunity, opportunity_id)
            self.assertIsNone(real_estate.planned_housing_units)
            self.assertIsNone(real_estate.estimated_works_end)
            self.assertIsNone(real_estate.estimated_rental_start)
            self.assertIsNone(real_estate.public_latitude)
            self.assertIsNone(real_estate.public_longitude)

    def test_minimum_contribution_is_optional_but_positive(self):
        with self.Session() as db:
            without_minimum = self.new_opportunity()
            db.add(without_minimum)
            db.add(self.new_opportunity(minimum_contribution_cents=500_00))
            db.commit()
            self.assertIsNone(without_minimum.minimum_contribution_cents)
        for invalid in (0, -1):
            with self.subTest(minimum_contribution_cents=invalid), self.Session() as db:
                db.add(self.new_opportunity(minimum_contribution_cents=invalid))
                with self.assertRaises(IntegrityError):
                    db.commit()

    def test_invalid_real_estate_values_are_rejected(self):
        invalid_cases = {
            "surface zero": {"surface_m2": Decimal("0")},
            "housing units zero": {
                "asset_type": AssetType.RESIDENTIAL, "planned_housing_units": 0,
            },
            "residential without housing units": {"asset_type": AssetType.RESIDENTIAL},
            "mixed without housing units": {"asset_type": AssetType.MIXED},
            "housing units on land": {"asset_type": AssetType.LAND, "planned_housing_units": 3},
            "housing units on commercial": {
                "asset_type": AssetType.COMMERCIAL, "planned_housing_units": 3,
            },
            "latitude out of range": {
                "public_latitude": Decimal("90.5"), "public_longitude": Decimal("2"),
            },
            "longitude out of range": {
                "public_latitude": Decimal("41"), "public_longitude": Decimal("-180.5"),
            },
            "only latitude": {"public_latitude": Decimal("41")},
            "only longitude": {"public_longitude": Decimal("2")},
            "works end without works": {
                "purpose": RealEstatePurpose.ACQUISITION,
                "estimated_works_end": date(2027, 1, 1),
            },
            "rental start on a sale": {
                "intended_use": IntendedUse.SALE,
                "estimated_rental_start": date(2027, 1, 1),
            },
        }
        for name, changes in invalid_cases.items():
            with self.subTest(name), self.assertRaises(IntegrityError):
                self.save_with_real_estate(**changes)

    def test_housing_units_follow_asset_type(self):
        # Obligatorias para residential y mixed; nulas para el resto.
        for asset_type in (AssetType.RESIDENTIAL, AssetType.MIXED):
            with self.subTest(asset_type=asset_type):
                self.save_with_real_estate(asset_type=asset_type, planned_housing_units=4)
        for asset_type in (AssetType.COMMERCIAL, AssetType.INDUSTRIAL, AssetType.LAND):
            with self.subTest(asset_type=asset_type):
                self.save_with_real_estate(asset_type=asset_type)

    def test_every_intended_use_is_accepted(self):
        for intended_use in IntendedUse:
            with self.subTest(intended_use=intended_use):
                opportunity_id = self.save_with_real_estate(intended_use=intended_use)
                with self.Session() as db:
                    stored = db.get(RealEstateOpportunity, opportunity_id)
                    self.assertEqual(stored.intended_use, intended_use)

    def test_works_end_allowed_for_every_purpose_with_works(self):
        for purpose in (
            RealEstatePurpose.CONSTRUCTION,
            RealEstatePurpose.RENOVATION,
            RealEstatePurpose.ACQUISITION_AND_RENOVATION,
        ):
            with self.subTest(purpose=purpose):
                self.save_with_real_estate(purpose=purpose, estimated_works_end=date(2027, 1, 1))

    def test_status_values_match_the_user_story(self):
        # «Financiación completada» se calcula; no existe un estado funded.
        with self.isolated.connect() as connection:
            labels = connection.scalars(text(
                "SELECT unnest(enum_range(NULL::opportunity_status))::text"
            )).all()
        self.assertEqual(labels, ["draft", "published", "rejected", "closed"])

    def test_valid_status_combinations(self):
        now = datetime.now(UTC)
        valid = [
            {"status": OpportunityStatus.DRAFT, "date_published": None},
            {"status": OpportunityStatus.REJECTED, "date_published": None},
            {"status": OpportunityStatus.PUBLISHED},
            {"status": OpportunityStatus.CLOSED, "date_closed": now},
        ]
        for changes in valid:
            with self.subTest(**changes), self.Session() as db:
                db.add(self.new_opportunity(**changes))
                db.commit()

    def test_invalid_status_combinations_are_rejected(self):
        now = datetime.now(UTC)
        invalid_cases = {
            "published without date_published": {
                "status": OpportunityStatus.PUBLISHED, "date_published": None,
            },
            "closed without date_published": {
                "status": OpportunityStatus.CLOSED, "date_published": None, "date_closed": now,
            },
            "closed without date_closed": {"status": OpportunityStatus.CLOSED},
            "date_closed on a published opportunity": {
                "status": OpportunityStatus.PUBLISHED, "date_closed": now,
            },
            "zero target": {"target_amount_cents": 0},
        }
        for name, changes in invalid_cases.items():
            with self.subTest(name), self.Session() as db:
                db.add(self.new_opportunity(**changes))
                with self.assertRaises(IntegrityError):
                    db.commit()

    def test_one_real_estate_record_per_opportunity(self):
        opportunity_id = self.save_with_real_estate()
        with self.Session() as db:
            db.add(self.real_estate(opportunity_id=opportunity_id))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_real_estate_record_needs_an_existing_parent(self):
        with self.Session() as db:
            db.add(self.real_estate(opportunity_id=999_999))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_deleting_the_parent_deletes_the_real_estate_record(self):
        # Borrado desde el ORM.
        opportunity_id = self.save_with_real_estate()
        with self.Session() as db:
            db.delete(db.get(Opportunity, opportunity_id))
            db.commit()
            self.assertIsNone(db.get(RealEstateOpportunity, opportunity_id))

        # Borrado directo en SQL: lo resuelve el ON DELETE CASCADE de la base de datos.
        opportunity_id = self.save_with_real_estate()
        with self.Session() as db:
            db.execute(delete(Opportunity).where(Opportunity.id == opportunity_id))
            db.commit()
            remaining = db.scalar(
                select(RealEstateOpportunity).where(
                    RealEstateOpportunity.opportunity_id == opportunity_id
                )
            )
            self.assertIsNone(remaining)


if __name__ == "__main__":
    unittest.main()
