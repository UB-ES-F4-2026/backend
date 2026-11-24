"""Executa només les proves d'integració de backend durant la transició.

Amb la variable d'entorn TEST_ORDER_SEED (un enter), barreja l'ordre de les classes
i el de les proves de cada classe. Cap prova pot dependre d'una altra: si una falla
només amb una llavor concreta, la mateixa llavor reprodueix l'ordre.
"""
import os
import random
import sys
import unittest
from pathlib import Path


TESTS_DIRECTORY = Path(__file__).parent
PROJECT_ROOT = TESTS_DIRECTORY.parent
UNIT_TEST_FILES = {"test_name_search.py"}


def is_integration_test(path: Path) -> bool:
    return path.name.startswith("test_") and path.name.endswith(".py") and (
        path.name not in UNIT_TEST_FILES and not path.name.endswith("_unit.py")
    )


def iter_tests(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def shuffled(suite: unittest.TestSuite, seed: int) -> unittest.TestSuite:
    """Barreja classes i proves, mantenint juntes les proves de cada classe.

    Les proves d'una classe comparteixen la base de dades de `setUpClass`; separar-les
    obligaria a recrear-la a cada canvi de classe.
    """
    by_class: dict[type, list[unittest.TestCase]] = {}
    for test in iter_tests(suite):
        by_class.setdefault(type(test), []).append(test)
    rng = random.Random(seed)
    classes = list(by_class)
    rng.shuffle(classes)
    ordered = unittest.TestSuite()
    for test_class in classes:
        tests = by_class[test_class]
        rng.shuffle(tests)
        ordered.addTests(tests)
    return ordered


def main() -> int:
    # Quan s'executa com a script, Python només afegeix `tests/` a sys.path.
    # Les proves d'integració importen el paquet real `app/` de l'arrel.
    sys.path.insert(0, str(PROJECT_ROOT))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for path in sorted(filter(is_integration_test, TESTS_DIRECTORY.glob("test_*.py"))):
        suite.addTests(loader.discover(str(TESTS_DIRECTORY), pattern=path.name))
    seed = os.environ.get("TEST_ORDER_SEED")
    if seed:
        print(f"Ordre aleatori de les proves: TEST_ORDER_SEED={int(seed)}", flush=True)
        suite = shuffled(suite, int(seed))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
