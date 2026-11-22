"""Gestors públics de webhooks per a integracions externes."""
import os

import stripe
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DbSession
from app.core.deposits import credit_stripe_deposit

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request, db: DbSession) -> dict[str, str]:
    """Acredita un wallet una sola vegada quan Stripe confirma el pagament."""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook is not configured",
        )

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, request.headers.get("stripe-signature"), webhook_secret
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook payload",
        ) from None
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        ) from None

    if isinstance(event, stripe.StripeObject):
        event = event.to_dict()
    if event.get("type") != "payment_intent.succeeded":
        return {"status": "ignored"}

    payment_intent = event.get("data", {}).get("object", {})
    metadata = payment_intent.get("metadata") or {}
    try:
        user_id = int(metadata.get("user_id"))
        amount_cents = int(
            payment_intent.get("amount_received") or payment_intent.get("amount")
        )
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe payment data",
        ) from None

    event_id = event.get("id")
    payment_intent_id = payment_intent.get("id")
    currency = (payment_intent.get("currency") or "").lower()
    if (
        not event_id
        or not payment_intent_id
        or amount_cents < 50
        or currency != "eur"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe payment data",
        )

    try:
        credited = credit_stripe_deposit(
            db,
            stripe_event_id=event_id,
            stripe_payment_intent_id=payment_intent_id,
            user_id=user_id,
            amount_cents=amount_cents,
            currency=currency,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"status": "success" if credited else "already_processed"}
