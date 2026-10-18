"""Every route requires a valid session unless it is explicitly public."""
import unittest

from fastapi.routing import APIRoute

from app.api.deps import get_current_user
from app.main import app

# Routes reachable without logging in. Docs and openapi.json are not APIRoutes.
PUBLIC_ROUTES = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/health"),
}


def depends_on(dependant, function) -> bool:
    return any(
        sub.call is function or depends_on(sub, function)
        for sub in dependant.dependencies
    )


class RouteProtectionTest(unittest.TestCase):
    def test_non_public_routes_require_a_session(self):
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                with self.subTest(method=method, path=route.path):
                    protected = depends_on(route.dependant, get_current_user)
                    public = (method, route.path) in PUBLIC_ROUTES
                    self.assertNotEqual(
                        protected, public,
                        "Add Depends(get_current_user) or list the route in PUBLIC_ROUTES",
                    )


if __name__ == "__main__":
    unittest.main()
