"""Executa només les proves d'integració de backend durant la transició."""
import unittest
from pathlib import Path


TESTS_DIRECTORY = Path(__file__).parent
UNIT_TEST_FILES = {"test_name_search.py"}


def is_integration_test(path: Path) -> bool:
    return path.name.startswith("test_") and path.name.endswith(".py") and (
        path.name not in UNIT_TEST_FILES and not path.name.endswith("_unit.py")
    )


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for path in sorted(filter(is_integration_test, TESTS_DIRECTORY.glob("test_*.py"))):
        suite.addTests(loader.discover(str(TESTS_DIRECTORY), pattern=path.name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
