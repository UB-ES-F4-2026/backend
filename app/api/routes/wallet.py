"""Routes for wallet balance and deposits."""

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.wallet import Wallet
from app.schemas.wallet import BalanceRead

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
