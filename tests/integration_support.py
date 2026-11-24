"""Base comuna de les proves d'integració que uneixen diversos mòduls per HTTP.

No és un fitxer de proves (no comença per `test_`): aplega la base de dades temporal
i els passos que es repeteixen perquè cada prova es llegeixi com el recorregut d'un
usuari. No se simula res: registre, inici de sessió, signatura de Stripe i fitxers
passen pel codi real. L'únic que no hi ha és la xarxa de Stripe.
"""
import hashlib
import hmac
import json
import os
import threading
import time
import unittest
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core import media
from app.core.security import SESSION_COOKIE, hash_session_token
from app.database import engine, get_db
from app.main import app
from app.models.commitment import Commitment
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.session import UserSession
from app.models.wallet import Wallet
from app.models.wallet_deposit import WalletDeposit

# Secret de proves: el mateix amb què se signen els esdeveniments i amb què els valida la ruta.
WEBHOOK_SECRET = "whsec_integration_test"
PASSWORD = "correct-horse"
VALID_IBAN = "ES9121000418450200051332"
MASKED_IBAN = "ES91****************1332"
PNG = b"\x89PNG\r\n\x1a\nimage"
WEBP = b"RIFF\x00\x00\x00\x00WEBPimage"
PNG_IMAGE = ("cover.png", PNG, "image/png")
WEBP_IMAGE = ("gallery.webp", WEBP, "image/webp")
# Marge perquè un fil acabi; si se supera, la prova falla en lloc de penjar-se.
THREAD_TIMEOUT = 30

UNAUTHORIZED = {"detail": "Invalid or missing session"}
INSUFFICIENT_BALANCE = {"detail": "Insufficient available balance"}
INSUFFICIENT_FUNDS = {"detail": "Insufficient funds"}
COMMITMENT_NOT_AVAILABLE = {"detail": "Opportunity not available"}
NOT_ACCEPTED = {"detail": "Opportunity no longer accepts this contribution"}
DETAIL_NOT_AVAILABLE = {"detail": "Oportunidad no disponible"}


@dataclass(frozen=True)
class Actor:
    """Usuari registrat amb la sessió iniciada en el seu propi client HTTP."""

    id: int
    email: str
    client: TestClient
    token: str

    @property
    def headers(self) -> dict[str, str]:
        """La cookie com a capçalera, per als clients sense memòria dels fils."""
        return {"Cookie": f"{SESSION_COOKIE}={self.token}"}


def new_email() -> str:
    return f"{uuid4().hex}@example.com"


def signature_header(
    payload: bytes, *, secret: str = WEBHOOK_SECRET, timestamp: int | None = None
) -> str:
    """Capçalera `Stripe-Signature` tal com la calcula Stripe: HMAC de «timestamp.cos»."""
    if timestamp is None:
        timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def payment_event(user_id: int, amount_cents: int, **payment_intent_changes) -> dict:
    """Esdeveniment `payment_intent.succeeded` amb identificadors propis de cada crida."""
    payment_intent = {
        "id": f"pi_{uuid4().hex}",
        "object": "payment_intent",
        "amount": amount_cents,
        "amount_received": amount_cents,
        "currency": "eur",
        "metadata": {"user_id": str(user_id)},
    }
    payment_intent.update(payment_intent_changes)
    return {
        "id": f"evt_{uuid4().hex}",
        "object": "event",
        "type": "payment_intent.succeeded",
        "data": {"object": payment_intent},
    }


def opportunity_body(**changes) -> dict:
    """Metadades vàlides d'una oportunitat immobiliària d'1.000,00 € amb mínim de 50,00 €."""
    body = {
        "type": "real_estate",
        "title": f"Rehabilitació {uuid4().hex[:8]}",
        "description": "Descripció de l'oportunitat.",
        "location": {"municipality": "Girona", "province": "Girona", "country": "Espanya"},
        "target_amount_cents": 100_000,
        "minimum_contribution_cents": 5_000,
        "deadline": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "real_estate": {
            "purpose": "acquisition_and_renovation",
            "intended_use": "rental",
            "asset_type": "residential",
            "surface_m2": "250.50",
            "planned_housing_units": 4,
            "estimated_works_end": None,
            "estimated_rental_start": None,
            "public_latitude": None,
            "public_longitude": None,
        },
    }
    body.update(changes)
    return body


class IntegrationTestCase(unittest.TestCase):
    """FastAPI real sobre una base PostgreSQL pròpia de la classe, migrada amb Alembic."""

    database_prefix = "integration_test_"

    @classmethod
    def setUpClass(cls):
        cls.database = cls.database_prefix + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        # Les proves de concurrència obren una connexió per petició simultània.
        cls.isolated = create_engine(
            engine.url.set(database=cls.database), pool_size=10, max_overflow=10
        )
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
        # Cada prova té el seu directori d'imatges: pot comprovar-ne tot el contingut
        # sense veure fitxers d'una altra prova.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(setattr, media, "MEDIA_ROOT", media.MEDIA_ROOT)
        media.MEDIA_ROOT = Path(directory.name)
        self.media_root = media.MEDIA_ROOT
        # L'entorn de CI deixa el secret buit i la ruta respondria 503.
        environment = patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET})
        environment.start()
        self.addCleanup(environment.stop)
        self.anonymous = self.new_client()

    # --- Usuaris i sessions -------------------------------------------------------

    @staticmethod
    def new_client() -> TestClient:
        # HTTPS perquè la cookie de sessió és `Secure`; cada client té les seves cookies.
        return TestClient(app, base_url="https://testserver")

    def register(self, client: TestClient, email: str, **changes) -> Response:
        body = {
            "email": email,
            "password": PASSWORD,
            "first_name": "Ana",
            "last_name": "Example",
            "phone": "+34612345678",
        }
        body.update(changes)
        return client.post("/api/auth/register", json=body)

    def log_in(self, email: str, client: TestClient | None = None) -> tuple[TestClient, str]:
        """Inicia sessió per la ruta real; retorna el client i el token de la cookie."""
        client = client or self.new_client()
        response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return client, client.cookies[SESSION_COOKIE]

    def new_actor(self, *, promoter: bool = False, available_cents: int = 0) -> Actor:
        """Registra un usuari nou, li inicia sessió i, si cal, li ingressa saldo."""
        email = new_email()
        changes = {}
        if promoter:
            changes["promoting_entity"] = {"legal_name": f"Promotora {uuid4().hex[:8]} SL"}
        client = self.new_client()
        registered = self.register(client, email, **changes)
        self.assertEqual(registered.status_code, 201, registered.text)
        _, token = self.log_in(email, client)
        actor = Actor(id=registered.json()["id"], email=email, client=client, token=token)
        if available_cents:
            self.deposit(actor.id, available_cents)
        return actor

    def expire_session(self, token: str) -> None:
        """Deixa la sessió caducada: el temps no es pot avançar d'una altra manera."""
        with self.Session() as db:
            session = db.scalar(
                select(UserSession).where(UserSession.token == hash_session_token(token))
            )
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()

    def session_tokens(self, user_id: int) -> list[str]:
        """Hashos de les sessions que l'usuari té desades."""
        with self.Session() as db:
            return list(
                db.scalars(select(UserSession.token).where(UserSession.user_id == user_id))
            )

    # --- Stripe -----------------------------------------------------------------------

    def post_event(
        self,
        event: dict | bytes,
        *,
        signature: str | None = None,
        client: TestClient | None = None,
    ) -> Response:
        """Envia un esdeveniment al webhook, signat de debò si no es diu el contrari."""
        payload = event if isinstance(event, bytes) else json.dumps(event).encode()
        return (client or self.anonymous).post(
            "/api/webhooks/stripe",
            content=payload,
            headers={
                "content-type": "application/json",
                "stripe-signature": signature or signature_header(payload),
            },
        )

    def deposit(self, user_id: int, amount_cents: int) -> None:
        """Ingressa saldo com a producció: amb l'esdeveniment signat de Stripe."""
        response = self.post_event(payment_event(user_id, amount_cents))
        self.assertEqual(
            (response.status_code, response.json()), (200, {"status": "success"})
        )

    # --- Oportunitats i diners ----------------------------------------------------

    def post_opportunity(
        self,
        client: TestClient,
        body: dict,
        images: list[tuple[str, bytes, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        files = [("metadata", (None, json.dumps(body)))]
        files.extend(("images", image) for image in (images or [PNG_IMAGE]))
        return client.post("/api/opportunities", files=files, headers=headers)

    def create_opportunity(
        self,
        promoter: Actor,
        *,
        publish: bool = False,
        images: list[tuple[str, bytes, str]] | None = None,
        **changes,
    ) -> dict:
        """Crea l'oportunitat per la ruta real, amb la sessió de l'entitat promotora."""
        response = self.post_opportunity(promoter.client, opportunity_body(**changes), images)
        self.assertEqual(response.status_code, 201, response.text)
        opportunity = response.json()
        if publish:
            self.publish(opportunity["id"])
        return opportunity

    def publish(self, opportunity_id: int) -> None:
        """Publica l'oportunitat per ORM: encara no hi ha cap ruta de revisió."""
        with self.Session() as db:
            opportunity = db.get(Opportunity, opportunity_id)
            opportunity.status = OpportunityStatus.PUBLISHED
            opportunity.date_published = datetime.now(UTC)
            db.commit()

    @staticmethod
    def commit(
        actor: Actor, opportunity_id: int, amount_cents: int, client: TestClient | None = None
    ) -> Response:
        return (client or actor.client).post(
            f"/api/opportunities/{opportunity_id}/commitments",
            json={"amount_cents": amount_cents},
            headers=actor.headers,
        )

    @staticmethod
    def withdraw(actor: Actor, amount_cents: int, client: TestClient | None = None) -> Response:
        return (client or actor.client).post(
            "/api/me/wallet/withdrawals",
            json={
                "amount_cents": amount_cents,
                "iban": VALID_IBAN,
                "account_holder": "Ada Lovelace",
            },
            headers=actor.headers,
        )

    def catalog_ids(self) -> list[int]:
        response = self.anonymous.get("/api/opportunities")
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.json()]

    # --- Estat desat ----------------------------------------------------------------

    def balances(self, user_id: int) -> tuple[int, int] | None:
        """Saldo (disponible, compromès) desat; `None` si l'usuari no té wallet."""
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
            return (wallet.available_cents, wallet.committed_cents) if wallet else None

    def commitments(self, **filters) -> list[Commitment]:
        with self.Session() as db:
            return list(
                db.scalars(select(Commitment).filter_by(**filters).order_by(Commitment.id))
            )

    def deposits(self, user_id: int) -> list[WalletDeposit]:
        with self.Session() as db:
            return list(
                db.scalars(
                    select(WalletDeposit)
                    .where(WalletDeposit.user_id == user_id)
                    .order_by(WalletDeposit.id)
                )
            )

    def opportunities_of(self, user_id: int) -> list[Opportunity]:
        with self.Session() as db:
            return list(
                db.scalars(
                    select(Opportunity)
                    .where(Opportunity.user_id == user_id)
                    .order_by(Opportunity.id)
                )
            )

    def opportunity_committed(self, opportunity_id: int) -> int:
        with self.Session() as db:
            return db.get(Opportunity, opportunity_id).committed_cents

    def stored_files(self) -> set[Path]:
        """Tots els fitxers del directori d'imatges de la prova, temporals inclosos."""
        return {
            path.relative_to(self.media_root)
            for path in self.media_root.rglob("*")
            if path.is_file()
        }

    # --- Concurrència ---------------------------------------------------------------

    @contextmanager
    def wallet_locked(self, user_id: int) -> Iterator[None]:
        """Reté el wallet bloquejat, com ho faria una operació que encara no ha acabat."""
        with self.isolated.connect() as connection:
            connection.execute(
                text("SELECT id FROM wallets WHERE user_id = :user_id FOR UPDATE"),
                {"user_id": user_id},
            )
            try:
                yield
            finally:
                connection.rollback()

    def wait_until_blocked(self, expected: int) -> None:
        """Espera que `expected` peticions estiguin aturades en un bloqueig de PostgreSQL.

        És una condició observada a `pg_stat_activity`, no una pausa a cegues: quan es
        compleix, totes les peticions són dins la seva transacció alhora.
        """
        deadline = time.monotonic() + THREAD_TIMEOUT
        waiting = 0
        while time.monotonic() < deadline:
            with self.isolated.connect() as connection:
                waiting = connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                    )
                )
            if waiting == expected:
                return
            time.sleep(0.02)
        self.fail(f"Només {waiting} de {expected} peticions han arribat al bloqueig")

    def simultaneous(
        self, calls: list[Callable[[TestClient], Response]], *, queued_behind_wallet_of: int
    ) -> list[Response]:
        """Executa les peticions alhora, cadascuna amb el seu client i la seva connexió.

        El wallet es reté bloquejat fins que totes hi han arribat i llavors s'allibera:
        la competència pel saldo és real a cada execució, no fruit de l'atzar dels fils.
        """
        barrier = threading.Barrier(len(calls))

        def run(call: Callable[[TestClient], Response]) -> Response:
            client = self.new_client()
            barrier.wait(timeout=THREAD_TIMEOUT)
            return call(client)

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            with self.wallet_locked(queued_behind_wallet_of):
                futures = [pool.submit(run, call) for call in calls]
                self.wait_until_blocked(len(calls))
            return [future.result(timeout=THREAD_TIMEOUT) for future in futures]
