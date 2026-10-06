"""Exercise real Alembic migrations against an isolated disposable database."""
import shutil
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, select, text

from app.database import Base, engine


class MigrationsTest(unittest.TestCase):
    def test_empty_database_creation_upgrade_and_data_preservation(self):
        database = "migration_test_" + uuid4().hex
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        isolated = create_engine(engine.url.set(database=database))
        try:
            with tempfile.TemporaryDirectory() as folder:
                scripts = Path(folder) / "alembic"
                shutil.copytree("/app/alembic", scripts)
                config = Config("/app/alembic.ini")
                config.set_main_option("script_location", str(scripts))

                def run(operation, *args, **kwargs):
                    with isolated.begin() as connection:
                        config.attributes["connection"] = connection
                        return operation(config, *args, **kwargs)

                run(command.upgrade, "head")
                probe = Table(
                    "migration_probe", Base.metadata,
                    Column("id", Integer, primary_key=True),
                    Column("value", String(80), nullable=False),
                )
                try:
                    run(command.revision, message="test create table", autogenerate=True)
                    run(command.upgrade, "head")
                    with isolated.begin() as connection:
                        connection.execute(probe.insert().values(id=1, value="preserved"))
                    probe.append_column(Column("note", String(80), nullable=True))
                    run(command.revision, message="test add column", autogenerate=True)
                    run(command.upgrade, "head")
                    run(command.upgrade, "head")
                    actual = Table("migration_probe", MetaData(), autoload_with=isolated)
                    with isolated.connect() as connection:
                        row = connection.execute(select(actual)).one()
                        self.assertEqual(row.value, "preserved")
                        self.assertIsNone(row.note)
                    self.assertIn("note", [c["name"] for c in inspect(isolated).get_columns("migration_probe")])
                    run(command.check)
                finally:
                    Base.metadata.remove(probe)
        finally:
            isolated.dispose()
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))


if __name__ == "__main__":
    unittest.main()
