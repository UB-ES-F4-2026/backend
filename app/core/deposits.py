"""Acreditacions atòmiques de pagaments Stripe confirmats."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.wallet import Wallet
from app.models.wallet_deposit import WalletDeposit


def credit_stripe_deposit(
    db: Session,
    *,
    stripe_event_id: str,
    stripe_payment_intent_id: str,
    user_id: int,
    amount_cents: int,
    currency: str,
) -> bool:
    """Registra i acredita un pagament una única vegada en la transacció rebuda."""
    deposit_id = db.scalar(
        insert(WalletDeposit)
        .values(
            stripe_event_id=stripe_event_id,
            stripe_payment_intent_id=stripe_payment_intent_id,
            user_id=user_id,
            amount_cents=amount_cents,
            currency=currency,
        )
        .on_conflict_do_nothing()
        .returning(WalletDeposit.id)
    )
    if deposit_id is None:
        return False

    wallet = db.scalar(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    )
    if wallet is None:
        wallet = Wallet(user_id=user_id)
        db.add(wallet)
        db.flush()
        wallet = db.scalar(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )

    if wallet is None:
        raise RuntimeError("Wallet could not be created")

    wallet.available_cents += amount_cents
    db.flush()
    return True
