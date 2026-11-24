"""Accés concurrent al saldo dels usuaris."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.wallet import Wallet


def lock_wallet(db: Session, user_id: int) -> Wallet | None:
    """Bloqueja el wallet de l'usuari fins que acabi la transacció actual.

    Tota operació que modifiqui un saldo (reserva, retirada, ingrés) l'ha de
    llegir amb aquesta funció abans de validar-lo: una segona operació sobre el
    mateix wallet s'espera i veu el saldo ja actualitzat per la primera.

    Si la mateixa transacció també bloqueja una oportunitat, l'oportunitat es
    bloqueja abans que el wallet, perquè dues operacions no s'esperin entre si.
    """
    return db.scalar(
        select(Wallet)
        .where(Wallet.user_id == user_id)
        .with_for_update()
        # Descarta l'estat que la sessió pogués tenir llegit abans del bloqueig.
        .execution_options(populate_existing=True)
    )
