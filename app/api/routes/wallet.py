"""Routes for wallet balance and deposits."""
import os

import stripe
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.wallet import Wallet
from app.schemas.wallet import BalanceRead, DepositIntentCreate, DepositIntentResponse

router = APIRouter(prefix="/api/me/wallet", tags=["wallet"])
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


@router.get("", response_model=BalanceRead)
def get_wallet_balance(
    current_user: CurrentUser,
    db: DbSession,
    response: Response,
) -> BalanceRead:
    response.headers["Cache-Control"] = "no-store"
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == current_user.id))
    return BalanceRead(available_cents=wallet.available_cents if wallet else 0)


@router.post("/deposit-intent", response_model=DepositIntentResponse)
def create_deposit_intent(
    body: DepositIntentCreate,
    current_user: CurrentUser,
) -> DepositIntentResponse:
    if not stripe.api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La clave secreta de Stripe no está configurada en el servidor.",
        )

    try:
        intent = stripe.PaymentIntent.create(
            amount=body.amount_cents,
            currency="eur",
            metadata={"user_id": str(current_user.id)},
        )
    except stripe.error.StripeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo crear el intento de pago.",
        ) from None

    return DepositIntentResponse(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
    )
