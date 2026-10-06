"""Apply committed migrations before starting the requested process."""
import logging
import os
import sys
import time

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import OperationalError

from app.database import engine


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = Config("/app/alembic.ini")
    for attempt in range(1, 16):
        try:
            command.upgrade(config, "head")
            break
        except OperationalError:
            if attempt == 15:
                raise
            logging.warning("Database unavailable; startup retry %d/15.", attempt)
            time.sleep(2)
    engine.dispose()
    if len(sys.argv) < 2:
        raise SystemExit("No application command provided")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
