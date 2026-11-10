"""Public Webhook handlers for external integrations."""
import os
import stripe
from fastapi import APIRouter, Request, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession
from app.models.wallet import Wallet
from app.models.wallet_deposit import WalletDeposit

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: DbSession):
    """Procesa eventos asíncronos enviados por Stripe tras la confirmación de pago."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El secreto del webhook de Stripe no está configurado."
        )

    try:
        # Verificar la autenticidad y firma de la petición
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Payload de webhook inválido."
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Firma del webhook de Stripe no válida."
        )

    if isinstance(event, stripe.StripeObject):
        event = event.to_dict()

    # Manejar el evento de pago completado exitosamente
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        metadata = payment_intent.get("metadata") or {}
        user_id_raw = metadata.get("user_id")
        payment_intent_id = payment_intent.get("id")
        event_id = event.get("id")
        currency = (payment_intent.get("currency") or "").lower()
        amount_cents = payment_intent.get("amount_received") or payment_intent.get("amount")

        try:
            user_id = int(user_id_raw)
            amount_cents = int(amount_cents)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los datos del pago no son válidos.",
            ) from None

        if not event_id or not payment_intent_id or amount_cents <= 0 or currency != "eur":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los datos del pago no son válidos.",
            )

        deposit_id = db.scalar(
            insert(WalletDeposit)
            .values(
                stripe_event_id=event_id,
                stripe_payment_intent_id=payment_intent_id,
                user_id=user_id,
                amount_cents=amount_cents,
                currency=currency,
            )
            .on_conflict_do_nothing()
            .returning(WalletDeposit.id)
        )
        if deposit_id is None:
            db.rollback()
            return {"status": "already_processed"}

        db.execute(
            insert(Wallet)
            .values(user_id=user_id, available_cents=0)
            .on_conflict_do_nothing(index_elements=[Wallet.user_id])
        )
        wallet = db.scalar(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        if wallet is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se encontró la wallet asociada al pago.",
            )

        wallet.available_cents += amount_cents
        db.commit()

    return {"status": "success"}