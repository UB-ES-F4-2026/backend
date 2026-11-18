"""Base comuna de compromisos i saldo reservat (US03.1), contra PostgreSQL real."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import UTC, datetime, timedelta
from unittest import mock
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.commitments import (
    CommitmentError,
    ExceedsRemainingCapital,
    InsufficientFunds,
    OpportunityNotFound,
    lock_opportunity,
    reserve_funds,
)
from app.database import engine
from app.models.commitment import Commitment
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.models.user import User
from app.models.wallet import Wallet

PREVIOUS_REVISION = "a6b27f4c91de"
# Marge perquè un fil acabi; si se supera, el test falla en lloc de penjar-se.
THREAD_TIMEOUT = 30


class CommitmentsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "commitments_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        # Les proves de concurrència obren una connexió per fil.
        cls.isolated = create_engine(
            engine.url.set(database=cls.database), pool_size=10, max_overflow=10
        )
        config = Config("/app/alembic.ini")
        with cls.isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        cls.Session = sessionmaker(bind=cls.isolated, autoflush=False, expire_on_commit=False)

        with cls.Session() as db:
            promoter = User(email="promoter@example.com", hashed_password="x" * 60)
            db.add(promoter)
            db.flush()
            db.add(PromotingEntity(user_id=promoter.id, legal_name="Promociones Girona SL"))
            db.commit()
            cls.promoter_id = promoter.id

    @classmethod
    def tearDownClass(cls):
        cls.isolated.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{cls.database}" WITH (FORCE)'))

    def create_user(self, available_cents: int | None) -> int:
        """Crea un usuari; amb `None`, sense fila de wallet."""
        with self.Session() as db:
            user = User(email=f"{uuid4().hex}@example.com", hashed_password="x" * 60)
            if available_cents is not None:
                user.wallet = Wallet(available_cents=available_cents)
            db.add(user)
            db.commit()
            return user.id

    def new_opportunity(self, **changes) -> Opportunity:
        values = {
            "user_id": self.promoter_id,
            "type": OpportunityType.REAL_ESTATE,
            "status": OpportunityStatus.PUBLISHED,
            "title": "Rehabilitació d'un edifici",
            "description": "Descripció.",
            "location": "Girona",
            "target_amount_cents": 72_000_00,
            "committed_cents": 45_000_00,
            "minimum_contribution_cents": 50_00,
            "deadline": datetime.now(UTC) + timedelta(days=30),
            "date_published": datetime.now(UTC),
        }
        values.update(changes)
        return Opportunity(**values)

    def create_opportunity(self, **changes) -> int:
        with self.Session() as db:
            opportunity = self.new_opportunity(**changes)
            db.add(opportunity)
            db.commit()
            return opportunity.id

    def reserve(self, user_id: int, opportunity_id: int, amount_cents: int) -> Commitment:
        """El que farà una ruta: reservar i confirmar en una sola transacció."""
        with self.Session() as db:
            commitment = reserve_funds(
                db, user_id=user_id, opportunity_id=opportunity_id, amount_cents=amount_cents
            )
            db.commit()
            return commitment

    def attempt(self, user_id, opportunity_id, amount_cents, barrier=None) -> str:
        """Com `reserve`, però retorna el resultat perquè el reculli un altre fil."""
        with self.Session() as db:
            if barrier is not None:
                barrier.wait(timeout=THREAD_TIMEOUT)
            try:
                reserve_funds(
                    db, user_id=user_id, opportunity_id=opportunity_id, amount_cents=amount_cents
                )
                db.commit()
                return "ok"
            except CommitmentError as error:
                db.rollback()
                return type(error).__name__

    def balances(self, user_id: int) -> tuple[int, int] | None:
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
            return (wallet.available_cents, wallet.committed_cents) if wallet else None

    def opportunity_committed(self, opportunity_id: int) -> int:
        with self.Session() as db:
            return db.get(Opportunity, opportunity_id).committed_cents

    def commitments(self, **filters) -> list[Commitment]:
        with self.Session() as db:
            return list(
                db.scalars(select(Commitment).filter_by(**filters).order_by(Commitment.id))
            )


class ReserveFundsTest(CommitmentsTestCase):
    def test_moves_the_amount_from_available_to_committed_balance(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()
        before = datetime.now(UTC) - timedelta(seconds=5)

        commitment = self.reserve(user_id, opportunity_id, 100_00)

        self.assertEqual(self.balances(user_id), (150_00, 100_00))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_100_00)
        (stored,) = self.commitments(user_id=user_id)
        self.assertEqual(stored.id, commitment.id)
        self.assertEqual(stored.opportunity_id, opportunity_id)
        self.assertEqual(stored.amount_cents, 100_00)
        self.assertGreater(stored.created_at, before)
        self.assertEqual(commitment.created_at, stored.created_at)

    def test_each_reservation_is_stored_as_its_own_commitment(self):
        user_id = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity()

        self.reserve(user_id, opportunity_id, 100_00)
        self.reserve(user_id, opportunity_id, 250_50)

        stored = self.commitments(user_id=user_id)
        self.assertEqual([c.amount_cents for c in stored], [100_00, 250_50])
        # El saldo compromès coincideix amb la suma dels compromisos de l'usuari.
        self.assertEqual(self.balances(user_id), (649_50, 350_50))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_350_50)

    def test_committed_amount_is_no_longer_available(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()
        self.reserve(user_id, opportunity_id, 250_00)

        # Només es pot gastar el saldo disponible: el compromès no compta.
        with self.assertRaises(InsufficientFunds) as raised:
            self.reserve(user_id, opportunity_id, 1)

        self.assertEqual(raised.exception.available_cents, 0)
        self.assertEqual(self.balances(user_id), (0, 250_00))

    def test_amount_can_complete_the_target_but_not_exceed_it(self):
        user_id = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity(
            target_amount_cents=72_000_00, committed_cents=71_500_00
        )

        self.reserve(user_id, opportunity_id, 500_00)
        self.assertEqual(self.opportunity_committed(opportunity_id), 72_000_00)

        with self.assertRaises(ExceedsRemainingCapital) as raised:
            self.reserve(user_id, opportunity_id, 1)
        self.assertEqual(raised.exception.remaining_cents, 0)
        self.assertEqual(self.balances(user_id), (500_00, 500_00))

    def test_amount_above_remaining_capital_changes_nothing(self):
        user_id = self.create_user(1_000_00)
        opportunity_id = self.create_opportunity(
            target_amount_cents=72_000_00, committed_cents=71_500_00
        )

        with self.assertRaises(ExceedsRemainingCapital) as raised:
            self.reserve(user_id, opportunity_id, 500_01)

        self.assertEqual(raised.exception.remaining_cents, 500_00)
        self.assertEqual(self.balances(user_id), (1_000_00, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), 71_500_00)
        self.assertEqual(self.commitments(user_id=user_id), [])

    def test_amount_above_available_balance_changes_nothing(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        with self.assertRaises(InsufficientFunds) as raised:
            self.reserve(user_id, opportunity_id, 300_00)

        self.assertEqual(raised.exception.available_cents, 250_00)
        self.assertEqual(self.balances(user_id), (250_00, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)
        self.assertEqual(self.commitments(user_id=user_id), [])

    def test_user_without_wallet_has_no_funds_and_gets_no_wallet(self):
        user_id = self.create_user(None)
        opportunity_id = self.create_opportunity()

        with self.assertRaises(InsufficientFunds) as raised:
            self.reserve(user_id, opportunity_id, 100_00)

        self.assertEqual(raised.exception.available_cents, 0)
        self.assertIsNone(self.balances(user_id))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)

    def test_unknown_opportunity_is_reported_without_touching_the_wallet(self):
        user_id = self.create_user(250_00)

        with self.assertRaises(OpportunityNotFound):
            self.reserve(user_id, 999_999_999, 100_00)

        self.assertEqual(self.balances(user_id), (250_00, 0))

    def test_amount_must_be_positive(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        for amount_cents in (0, -100):
            with self.subTest(amount_cents=amount_cents), self.assertRaises(ValueError):
                self.reserve(user_id, opportunity_id, amount_cents)

        self.assertEqual(self.balances(user_id), (250_00, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)

    def test_state_and_deadline_are_left_to_the_caller(self):
        # La creació d'una oportunitat reserva l'aportació inicial abans de publicar-la.
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity(
            status=OpportunityStatus.DRAFT,
            date_published=None,
            committed_cents=0,
            deadline=datetime.now(UTC) - timedelta(days=1),
        )

        self.reserve(user_id, opportunity_id, 100_00)

        self.assertEqual(self.balances(user_id), (150_00, 100_00))
        self.assertEqual(self.opportunity_committed(opportunity_id), 100_00)

    def test_lock_opportunity_returns_the_current_row_or_reports_it_missing(self):
        opportunity_id = self.create_opportunity()
        with self.Session() as db:
            stale = db.get(Opportunity, opportunity_id)
            self.reserve(self.create_user(250_00), opportunity_id, 100_00)

            locked = lock_opportunity(db, opportunity_id)

            # El bloqueig rellegeix la fila: no retorna l'estat antic de la sessió.
            self.assertIs(locked, stale)
            self.assertEqual(locked.committed_cents, 45_100_00)
            with self.assertRaises(OpportunityNotFound):
                lock_opportunity(db, 999_999_999)

    def test_commitments_survive_attempts_to_delete_their_user_or_opportunity(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()
        self.reserve(user_id, opportunity_id, 100_00)

        for table, row_id in (("opportunities", opportunity_id), ("users", user_id)):
            with self.subTest(table=table), self.Session() as db:
                with self.assertRaises(IntegrityError):
                    db.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id})
                db.rollback()

        self.assertEqual(len(self.commitments(user_id=user_id)), 1)
        self.assertEqual(self.balances(user_id), (150_00, 100_00))

    def test_database_rejects_non_positive_commitments(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        with self.Session() as db:
            db.add(Commitment(user_id=user_id, opportunity_id=opportunity_id, amount_cents=0))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


class ReserveFundsAtomicityTest(CommitmentsTestCase):
    def test_nothing_is_stored_until_the_caller_commits(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        with self.Session() as db:
            reserve_funds(
                db, user_id=user_id, opportunity_id=opportunity_id, amount_cents=100_00
            )
            # Qui la crida falla després de reservar i abandona la transacció.
            db.rollback()

        self.assertEqual(self.balances(user_id), (250_00, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)
        self.assertEqual(self.commitments(user_id=user_id), [])

    def test_failure_half_way_through_leaves_no_partial_changes(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        # Falla un cop el saldo i el capital ja s'han modificat a la sessió.
        with mock.patch("app.core.commitments.Commitment", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.reserve(user_id, opportunity_id, 100_00)

        self.assertEqual(self.balances(user_id), (250_00, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)
        self.assertEqual(self.commitments(user_id=user_id), [])

    def test_database_failure_while_saving_leaves_no_partial_changes(self):
        user_id = self.create_user(250_00)
        opportunity_id = self.create_opportunity()

        # La base de dades rebutja el compromís quan ja ha rebut els altres canvis.
        with self.Session() as db:
            db.execute(text(
                "ALTER TABLE commitments ADD CONSTRAINT reject_everything CHECK (false) NOT VALID"
            ))
            db.commit()
        try:
            with self.assertRaises(IntegrityError):
                self.reserve(user_id, opportunity_id, 100_00)
        finally:
            with self.Session() as db:
                db.execute(text("ALTER TABLE commitments DROP CONSTRAINT reject_everything"))
                db.commit()

        self.assertEqual(self.balances(user_id), (250_00, 0))
        self.assertEqual(self.opportunity_committed(opportunity_id), 45_000_00)
        self.assertEqual(self.commitments(user_id=user_id), [])

    def test_opportunity_and_initial_reservation_are_created_together_or_not_at_all(self):
        user_id = self.create_user(250_00)

        def create_with_initial_contribution(db, amount_cents: int) -> int:
            opportunity = self.new_opportunity(
                status=OpportunityStatus.DRAFT, date_published=None, committed_cents=0
            )
            db.add(opportunity)
            db.flush()
            reserve_funds(
                db, user_id=user_id, opportunity_id=opportunity.id, amount_cents=amount_cents
            )
            return opportunity.id

        with self.Session() as db:
            with self.assertRaises(InsufficientFunds):
                create_with_initial_contribution(db, 300_00)
            db.rollback()
            rejected = db.scalar(
                select(func.count()).select_from(Opportunity).where(
                    Opportunity.status == OpportunityStatus.DRAFT
                )
            )
        self.assertEqual(rejected, 0)
        self.assertEqual(self.balances(user_id), (250_00, 0))

        with self.Session() as db:
            opportunity_id = create_with_initial_contribution(db, 100_00)
            db.commit()
        self.assertEqual(self.opportunity_committed(opportunity_id), 100_00)
        self.assertEqual(self.balances(user_id), (150_00, 100_00))


class ReserveFundsConcurrencyTest(CommitmentsTestCase):
    def test_second_reservation_waits_for_the_first_and_sees_its_balance(self):
        user_id = self.create_user(100_00)
        # Oportunitats diferents: l'únic que comparteixen és el wallet.
        first_opportunity = self.create_opportunity()
        second_opportunity = self.create_opportunity()
        first_reserved = threading.Event()
        release_first = threading.Event()

        def first() -> None:
            with self.Session() as db:
                reserve_funds(
                    db, user_id=user_id, opportunity_id=first_opportunity, amount_cents=80_00
                )
                first_reserved.set()
                release_first.wait(timeout=THREAD_TIMEOUT)
                db.commit()

        def second() -> str:
            first_reserved.wait(timeout=THREAD_TIMEOUT)
            return self.attempt(user_id, second_opportunity, 80_00)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_result = pool.submit(first)
            second_result = pool.submit(second)
            try:
                self.assertTrue(first_reserved.wait(timeout=THREAD_TIMEOUT))
                # La segona no pot acabar mentre la primera té el wallet bloquejat.
                with self.assertRaises(FutureTimeout):
                    second_result.result(timeout=1)
            finally:
                release_first.set()
            first_result.result(timeout=THREAD_TIMEOUT)
            self.assertEqual(second_result.result(timeout=THREAD_TIMEOUT), "InsufficientFunds")

        self.assertEqual(self.balances(user_id), (20_00, 80_00))
        self.assertEqual(self.opportunity_committed(first_opportunity), 45_080_00)
        self.assertEqual(self.opportunity_committed(second_opportunity), 45_000_00)

    def test_simultaneous_reservations_never_spend_more_than_the_balance(self):
        user_id = self.create_user(100_00)
        opportunities = [self.create_opportunity() for _ in range(8)]
        barrier = threading.Barrier(len(opportunities))

        with ThreadPoolExecutor(max_workers=len(opportunities)) as pool:
            futures = [
                pool.submit(self.attempt, user_id, opportunity_id, 30_00, barrier)
                for opportunity_id in opportunities
            ]
            results = [future.result(timeout=THREAD_TIMEOUT) for future in futures]

        # Amb 100,00 € només hi caben tres reserves de 30,00 €.
        self.assertEqual(results.count("ok"), 3)
        self.assertEqual(results.count("InsufficientFunds"), 5)
        self.assertEqual(self.balances(user_id), (10_00, 90_00))
        stored = self.commitments(user_id=user_id)
        self.assertEqual(sum(c.amount_cents for c in stored), 90_00)
        for opportunity_id, result in zip(opportunities, results):
            expected = 45_030_00 if result == "ok" else 45_000_00
            self.assertEqual(self.opportunity_committed(opportunity_id), expected)

    def test_simultaneous_reservations_never_exceed_the_remaining_capital(self):
        opportunity_id = self.create_opportunity(
            target_amount_cents=72_000_00, committed_cents=71_500_00
        )
        users = [self.create_user(1_000_00) for _ in range(8)]
        barrier = threading.Barrier(len(users))

        with ThreadPoolExecutor(max_workers=len(users)) as pool:
            futures = [
                pool.submit(self.attempt, user_id, opportunity_id, 300_00, barrier)
                for user_id in users
            ]
            results = [future.result(timeout=THREAD_TIMEOUT) for future in futures]

        # Falten 500,00 €: només hi cap una aportació de 300,00 €.
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("ExceedsRemainingCapital"), 7)
        self.assertEqual(self.opportunity_committed(opportunity_id), 71_800_00)
        stored = self.commitments(opportunity_id=opportunity_id)
        self.assertEqual([c.amount_cents for c in stored], [300_00])
        for user_id, result in zip(users, results):
            expected = (700_00, 300_00) if result == "ok" else (1_000_00, 0)
            self.assertEqual(self.balances(user_id), expected)


class CommitmentsMigrationTest(unittest.TestCase):
    def test_existing_wallets_keep_their_balance_and_start_with_nothing_committed(self):
        database = "commitments_migration_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        isolated = create_engine(engine.url.set(database=database))
        config = Config("/app/alembic.ini")

        def migrate(operation, revision: str) -> None:
            with isolated.begin() as connection:
                config.attributes["connection"] = connection
                operation(config, revision)

        try:
            migrate(command.upgrade, PREVIOUS_REVISION)
            with isolated.begin() as connection:
                user_id = connection.scalar(
                    text(
                        "INSERT INTO users (email, hashed_password) "
                        "VALUES (:email, :password) RETURNING id"
                    ),
                    {"email": f"{uuid4().hex}@example.com", "password": "x" * 60},
                )
                connection.execute(
                    text("INSERT INTO wallets (user_id, available_cents) VALUES (:id, 12345)"),
                    {"id": user_id},
                )

            migrate(command.upgrade, "head")
            with isolated.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT available_cents, committed_cents FROM wallets "
                        "WHERE user_id = :id"
                    ),
                    {"id": user_id},
                ).one()
            self.assertEqual(tuple(row), (12345, 0))
            self.assertIn("commitments", inspect(isolated).get_table_names())

            migrate(command.downgrade, PREVIOUS_REVISION)
            inspector = inspect(isolated)
            self.assertNotIn("commitments", inspector.get_table_names())
            self.assertNotIn(
                "committed_cents", [c["name"] for c in inspector.get_columns("wallets")]
            )
            with isolated.connect() as connection:
                available = connection.scalar(
                    text("SELECT available_cents FROM wallets WHERE user_id = :id"),
                    {"id": user_id},
                )
            self.assertEqual(available, 12345)
        finally:
            isolated.dispose()
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))


if __name__ == "__main__":
    unittest.main()
