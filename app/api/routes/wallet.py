"""Rutes per consultar el saldo, ingressar fons i simular retirades."""
import os

import stripe
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.withdrawals import InsufficientAvailableBalance, withdraw_funds
from app.models.wallet import Wallet
from app.schemas.wallet import (
    BalanceRead,
    DepositIntentCreate,
    DepositIntentResponse,
    WithdrawalRead,
    WithdrawalRequest,
)

router = APIRouter(prefix="/api/me/wallet", tags=["wallet"])


@router.get("", response_model=BalanceRead)
def get_wallet_balance(
    current_user: CurrentUser,
    db: DbSession,
    response: Response,
) -> BalanceRead:
    response.headers["Cache-Control"] = "no-store"
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == current_user.id))
    return BalanceRead(
        available_cents=wallet.available_cents if wallet else 0,
        committed_cents=wallet.committed_cents if wallet else 0,
    )


@router.post("/deposit-intent", response_model=DepositIntentResponse)
def create_deposit_intent(
    body: DepositIntentCreate,
    current_user: CurrentUser,
) -> DepositIntentResponse:
    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured",
        )

    stripe.api_key = stripe_secret_key
    try:
        intent = stripe.PaymentIntent.create(
            amount=body.amount_cents,
            currency="eur",
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata={"user_id": str(current_user.id)},
        )
    except stripe.error.StripeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe could not create the payment intent",
        ) from None

    return DepositIntentResponse(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
    )


@router.post("/withdrawals", response_model=WithdrawalRead)
def create_withdrawal(
    body: WithdrawalRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> WithdrawalRead:
    try:
        wallet = withdraw_funds(
            db, user_id=current_user.id, amount_cents=body.amount_cents
        )
        db.commit()
    except InsufficientAvailableBalance:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insufficient available balance",
        ) from None

    return WithdrawalRead(
        amount_cents=body.amount_cents,
        masked_iban=mask_iban(body.iban),
        account_holder=body.account_holder,
        available_cents=wallet.available_cents,
    )


def mask_iban(iban: str) -> str:
    return f"{iban[:4]}{'*' * (len(iban) - 8)}{iban[-4:]}"
