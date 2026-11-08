"""Toda ruta exige una sesión válida salvo que sea explícitamente pública."""
import re
import unittest

from fastapi.testclient import TestClient

from app.main import app

# Rutas accesibles sin iniciar sesión. La documentación y openapi.json no figuran en las rutas del esquema.
PUBLIC_ROUTES = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/health"),
    ("GET", "/api/opportunities"),
    ("GET", "/api/opportunities/{opportunity_id}"),
    ("GET", "/api/promotingentity"),
}


def schema_routes() -> set[tuple[str, str]]:
    # El esquema OpenAPI lista todas las rutas, incluidas las de los routers incluidos.
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


class RouteProtectionTest(unittest.TestCase):
    def test_public_routes_exist(self):
        self.assertLessEqual(PUBLIC_ROUTES, schema_routes())

    def test_non_public_routes_reject_requests_without_session(self):
        client = TestClient(app, base_url="https://testserver")
        for method, path in sorted(schema_routes() - PUBLIC_ROUTES):
            with self.subTest(method=method, path=path):
                # La sesión se comprueba antes de validar el cuerpo, así que no hace falta enviarlo.
                url = re.sub(r"\{[^}]+\}", "1", path)
                response = client.request(method, url)
                self.assertEqual(
                    response.status_code, 401,
                    "Añade CurrentUser / Depends(get_current_user) o incluye la ruta en PUBLIC_ROUTES",
                )


if __name__ == "__main__":
    unittest.main()
