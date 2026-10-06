"""Use the same connection settings and model metadata as the backend."""
from alembic import context
from sqlalchemy import text

from app.database import Base, database_url, engine
from app.model_registry import load_models

load_models()
target_metadata = Base.metadata


def run_with_connection(connection):
    # Prevent concurrent backend startups from applying the same revision.
    connection.execute(text("SELECT pg_advisory_xact_lock(7062026)"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    provided_connection = context.config.attributes.get("connection")
    if provided_connection is not None:
        run_with_connection(provided_connection)
    else:
        with engine.begin() as connection:
            run_with_connection(connection)
