"""API readiness includes a real PostgreSQL query."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import auth, opportunities, promoting_entity
from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(title="Fintech API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(opportunities.router)
app.include_router(promoting_entity.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok", "service": "backend", "database": "ok"}
