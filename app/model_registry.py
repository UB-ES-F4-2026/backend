"""Import every model module before Alembic inspects Base.metadata."""
import importlib
import pkgutil

from app import models


def load_models() -> None:
    for module in sorted(
        pkgutil.walk_packages(models.__path__, models.__name__ + "."),
        key=lambda item: item.name,
    ):
        importlib.import_module(module.name)
