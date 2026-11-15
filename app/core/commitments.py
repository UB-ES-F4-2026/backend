"""Base comuna per comprometre saldo en una oportunitat.

Les rutes que comprometen una aportació o una inversió, i la creació d'una
oportunitat amb aportació inicial, fan servir `reserve_funds`. Cap funció
d'aquest mòdul fa `commit()`: la transacció és de qui les crida, que també
tradueix les excepcions a la resposta HTTP que li correspongui.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.wallet import lock_wallet
from app.models.commitment import Commitment
from app.models.opportunity import Opportunity


class CommitmentError(Exception):
    """Una reserva no s'ha pogut fer; no s'ha modificat cap dada."""


class OpportunityNotFound(CommitmentError):
    def __init__(self, opportunity_id: int) -> None:
        super().__init__(f"Opportunity {opportunity_id} not found")
        self.opportunity_id = opportunity_id


class ExceedsRemainingCapital(CommitmentError):
    def __init__(self, amount_cents: int, remaining_cents: int) -> None:
        super().__init__("Amount exceeds the remaining capital of the opportunity")
        self.amount_cents = amount_cents
        self.remaining_cents = remaining_cents


class InsufficientFunds(CommitmentError):
    def __init__(self, amount_cents: int, available_cents: int) -> None:
        super().__init__("Insufficient available balance")
        self.amount_cents = amount_cents
        self.available_cents = available_cents


def lock_opportunity(db: Session, opportunity_id: int) -> Opportunity:
    """Bloqueja l'oportunitat fins que acabi la transacció actual.

    Qui hagi de comprovar l'estat o el termini abans de reservar ho fa sobre
    l'oportunitat que retorna aquesta funció, dins la mateixa transacció que
    `reserve_funds`: així ningú la pot canviar entre la comprovació i la reserva.
    """
    opportunity = db.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .with_for_update(of=Opportunity)
        # Descarta l'estat que la sessió pogués tenir llegit abans del bloqueig.
        .execution_options(populate_existing=True)
    )
    if opportunity is None:
        raise OpportunityNotFound(opportunity_id)
    return opportunity


def reserve_funds(
    db: Session, *, user_id: int, opportunity_id: int, amount_cents: int
) -> Commitment:
    """Traspassa `amount_cents` del saldo disponible al compromès i el registra.

    Dins la transacció de qui la crida: bloqueja l'oportunitat i després el
    wallet, valida l'import contra el capital pendent i el saldo disponible,
    i actualitza compromís, saldo i capital compromès de l'oportunitat. Si qui
    la crida no fa `commit()`, no queda cap dels tres canvis.

    Només valida el que és cert per a qualsevol reserva. L'estat, el termini,
    l'import mínim i el tipus d'oportunitat són responsabilitat de qui la crida.
    Una oportunitat creada a la mateixa transacció ha d'haver passat per
    `flush()` abans.

    Llança `OpportunityNotFound`, `ExceedsRemainingCapital` o
    `InsufficientFunds` sense haver modificat res. Els bloquejos es mantenen
    fins que qui la crida fa `rollback()` o `commit()`.
    """
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")

    opportunity = lock_opportunity(db, opportunity_id)
    wallet = lock_wallet(db, user_id)

    remaining_cents = opportunity.target_amount_cents - opportunity.committed_cents
    if amount_cents > remaining_cents:
        raise ExceedsRemainingCapital(amount_cents, max(remaining_cents, 0))
    # Un usuari sense wallet té saldo zero, igual que a la consulta del saldo.
    available_cents = wallet.available_cents if wallet else 0
    if amount_cents > available_cents:
        raise InsufficientFunds(amount_cents, available_cents)

    wallet.available_cents -= amount_cents
    wallet.committed_cents += amount_cents
    opportunity.committed_cents += amount_cents
    commitment = Commitment(
        user_id=user_id, opportunity_id=opportunity_id, amount_cents=amount_cents
    )
    db.add(commitment)
    db.flush()
    return commitment
