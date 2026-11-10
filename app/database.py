"""SQLAlchemy connection and session dependency shared by all models/routes."""
import os
from collections.abc import Generator

from sqlalchemy import MetaData, URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


database_url = URL.create(
    "postgresql+psycopg",
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    database=os.environ["POSTGRES_DB"],
)
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
    max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
    connect_args={"connect_timeout": 3},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Use Depends(get_db); each request receives its own session."""
    with SessionLocal() as session:
        yield session
