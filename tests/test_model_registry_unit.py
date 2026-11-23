"""Proves unitàries del registre de models per a Alembic."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.model_registry import load_models


class ModelRegistryTest(unittest.TestCase):
    def test_load_models_imports_every_discovered_module_in_name_order(self):
        discovered_modules = [
            SimpleNamespace(name="app.models.wallet"),
            SimpleNamespace(name="app.models.auth"),
            SimpleNamespace(name="app.models.opportunity"),
        ]

        with (
            patch("app.model_registry.pkgutil.walk_packages", return_value=discovered_modules),
            patch("app.model_registry.importlib.import_module") as import_module,
        ):
            load_models()

        self.assertEqual(
            [call.args[0] for call in import_module.call_args_list],
            [
                "app.models.auth",
                "app.models.opportunity",
                "app.models.wallet",
            ],
        )


if __name__ == "__main__":
    unittest.main()
