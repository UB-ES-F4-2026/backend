"""Operacions atòmiques de retirada simulada."""
from sqlalchemy.orm import Session

from app.core.wallet import lock_wallet
from app.models.wallet import Wallet


class InsufficientAvailableBalance(Exception):
    """La retirada supera el saldo disponible de l'usuari."""


def withdraw_funds(db: Session, *, user_id: int, amount_cents: int) -> Wallet:
    """Descompta saldo disponible dins de la transacció que rep.

    El bloqueig de fila fa que qualsevol altra operació sobre el mateix wallet
    esperi fins al ``commit()`` o ``rollback()``. Per això la comprovació del
    saldo i el descompte són atòmics entre retirades concurrents.
    """
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")

    wallet = lock_wallet(db, user_id)
    available_cents = wallet.available_cents if wallet else 0
    if amount_cents > available_cents:
        raise InsufficientAvailableBalance()

    wallet.available_cents -= amount_cents
    db.flush()
    return wallet
