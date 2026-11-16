"""Rutes per consultar el saldo i simular retirades."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.withdrawals import InsufficientAvailableBalance, withdraw_funds
from app.models.wallet import Wallet
from app.schemas.wallet import BalanceRead, WithdrawalRead, WithdrawalRequest

router = APIRouter(prefix="/api/me/wallet", tags=["wallet"])


@router.get("", response_model=BalanceRead)
def get_wallet_balance(
    current_user: CurrentUser,
    db: DbSession,
    response: Response,
) -> BalanceRead:
    response.headers["Cache-Control"] = "no-store"
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == current_user.id))
    return BalanceRead(available_cents=wallet.available_cents if wallet else 0)


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
