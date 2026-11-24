"""La sessió com a única porta de totes les rutes protegides (US01.8, US04.1).

`test_auth.py` comprova el tancament i la caducitat contra `/api/auth/me`; aquí es
comprova que la mateixa cookie deixa de servir a la resta de rutes, sobretot a les
que mouen diners, i que un compte no veu mai dades d'un altre.
"""
import re
import unittest

from app.core.security import SESSION_COOKIE, hash_session_token
from integration_support import (
    UNAUTHORIZED,
    VALID_IBAN,
    IntegrationTestCase,
)
from test_route_protection import PUBLIC_ROUTES, schema_routes

EMPTY_WALLET = {"available_cents": 0, "committed_cents": 0, "currency": "eur"}


def protected_routes() -> list[tuple[str, str]]:
    """Rutes de l'esquema que exigeixen sessió, amb un identificador qualsevol al camí."""
    return [
        (method, re.sub(r"\{[^}]+\}", "1", path))
        for method, path in sorted(schema_routes() - PUBLIC_ROUTES)
    ]


class SessionProtectionTest(IntegrationTestCase):
    database_prefix = "session_protection_integration_test_"

    def test_logout_closes_only_the_presented_session(self):
        user = self.new_actor()
        other_device, other_token = self.log_in(user.email)
        self.assertNotEqual(user.token, other_token)
        self.assertEqual(len(self.session_tokens(user.id)), 2)

        response = user.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(user.client.cookies.get(SESSION_COOKIE))
        self.assertEqual(self.session_tokens(user.id), [hash_session_token(other_token)])
        still_open = other_device.get("/api/auth/me")
        self.assertEqual(still_open.status_code, 200)
        self.assertEqual(still_open.json()["email"], user.email)

        # Repetir el tancament amb la cookie antiga no és cap error ni tanca res més.
        repeated = self.anonymous.post("/api/auth/logout", headers=user.headers)

        self.assertEqual((repeated.status_code, repeated.json()), (401, UNAUTHORIZED))
        self.assertEqual(self.session_tokens(user.id), [hash_session_token(other_token)])
        self.assertEqual(other_device.get("/api/me/wallet").status_code, 200)

    def test_user_can_log_in_again_after_logout(self):
        user = self.new_actor()
        self.assertEqual(user.client.post("/api/auth/logout").status_code, 204)

        _, token = self.log_in(user.email, user.client)

        self.assertNotEqual(token, user.token)
        self.assertEqual(user.client.get("/api/auth/me").json()["id"], user.id)
        self.assertEqual(self.session_tokens(user.id), [hash_session_token(token)])

    def test_logged_out_cookie_is_rejected_by_every_protected_route(self):
        user = self.new_actor()
        # La cookie era vàlida: el 401 de després és pel tancament, no per un token mal copiat.
        self.assertEqual(
            self.anonymous.get("/api/auth/me", headers=user.headers).status_code, 200
        )
        self.assertEqual(user.client.post("/api/auth/logout").status_code, 204)

        for method, url in protected_routes():
            with self.subTest(method=method, url=url):
                response = self.new_client().request(method, url, headers=user.headers)

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), UNAUTHORIZED)
        self.assertEqual(self.session_tokens(user.id), [])

    def test_expired_session_is_rejected_and_removed_on_every_protected_route(self):
        user = self.new_actor()

        for method, url in protected_routes():
            with self.subTest(method=method, url=url):
                client, token = self.log_in(user.email)
                self.expire_session(token)

                response = client.request(method, url)

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), UNAUTHORIZED)
                # La resposta esborra la cookie del navegador i la sessió de la base de dades.
                cleared = response.headers["set-cookie"].lower()
                self.assertTrue(cleared.startswith(f"{SESSION_COOKIE}="), cleared)
                self.assertIn("max-age=0", cleared)
                self.assertIsNone(client.cookies.get(SESSION_COOKIE))
                self.assertNotIn(hash_session_token(token), self.session_tokens(user.id))

        # La sessió que no ha caducat continua oberta.
        self.assertEqual(self.session_tokens(user.id), [hash_session_token(user.token)])
        self.assertEqual(user.client.get("/api/auth/me").status_code, 200)

    def test_closed_or_expired_session_cannot_move_money(self):
        promoter = self.new_actor(promoter=True)
        opportunity_id = self.create_opportunity(promoter, publish=True)["id"]
        investor = self.new_actor(available_cents=20_000)
        requests = {
            "commitment": (
                f"/api/opportunities/{opportunity_id}/commitments",
                {"amount_cents": 10_000},
            ),
            "withdrawal": (
                "/api/me/wallet/withdrawals",
                {"amount_cents": 10_000, "iban": VALID_IBAN, "account_holder": "Ada Lovelace"},
            ),
        }

        for state in ("closed", "expired"):
            for name, (url, body) in requests.items():
                with self.subTest(state=state, request=name):
                    client, token = self.log_in(investor.email)
                    if state == "closed":
                        self.assertEqual(client.post("/api/auth/logout").status_code, 204)
                    else:
                        self.expire_session(token)

                    response = client.post(
                        url, json=body, headers={"Cookie": f"{SESSION_COOKIE}={token}"}
                    )

                    self.assertEqual((response.status_code, response.json()), (401, UNAUTHORIZED))
                    self.assertEqual(self.balances(investor.id), (20_000, 0))
                    self.assertEqual(self.commitments(user_id=investor.id), [])
                    self.assertEqual(self.opportunity_committed(opportunity_id), 0)

        # Les mateixes peticions amb la sessió vigent sí que tenen efecte.
        for name, (url, body) in requests.items():
            accepted = investor.client.post(url, json=body)
            self.assertIn(accepted.status_code, (200, 201), f"{name}: {accepted.text}")
        self.assertEqual(self.balances(investor.id), (0, 10_000))

    def test_two_accounts_never_see_each_others_data(self):
        promoter = self.new_actor(promoter=True)
        opportunity_id = self.create_opportunity(promoter, publish=True)["id"]
        first = self.new_actor(available_cents=12_345)
        self.assertEqual(self.commit(first, opportunity_id, 5_000).status_code, 201)
        second = self.new_actor()
        first_wallet = {"available_cents": 7_345, "committed_cents": 5_000, "currency": "eur"}

        # Un mateix navegador: la primera persona tanca la sessió i hi entra la segona.
        browser, _ = self.log_in(first.email)
        self.assertEqual(browser.get("/api/me/wallet").json(), first_wallet)
        self.assertEqual(browser.post("/api/auth/logout").status_code, 204)
        self.assertEqual(browser.get("/api/me/wallet").status_code, 401)
        self.log_in(second.email, browser)

        self.assertEqual(browser.get("/api/auth/me").json()["email"], second.email)
        wallet = browser.get("/api/me/wallet")
        self.assertEqual(wallet.json(), EMPTY_WALLET)
        # Sense memòria cau, el saldo d'un compte no es pot servir a l'altre.
        self.assertEqual(wallet.headers["cache-control"], "no-store")
        self.assertEqual(
            browser.get("/api/me/commitments").json(),
            {
                "summary": {
                    "total_committed_cents": 0,
                    "commitments_count": 0,
                    "in_funding_count": 0,
                },
                "commitments": [],
            },
        )
        # L'altre dispositiu de la primera persona continua veient les seves dades.
        self.assertEqual(first.client.get("/api/me/wallet").json(), first_wallet)
        self.assertEqual(
            first.client.get("/api/me/commitments").json()["summary"]["total_committed_cents"],
            5_000,
        )

        # Un ingrés de la segona persona només canvia la seva cartera.
        self.deposit(second.id, 2_000)

        self.assertEqual(browser.get("/api/me/wallet").json()["available_cents"], 2_000)
        self.assertEqual(first.client.get("/api/me/wallet").json(), first_wallet)

        # Canviar de compte sense tancar la sessió substitueix la cookie de l'anterior.
        self.log_in(first.email, browser)

        self.assertEqual(browser.get("/api/auth/me").json()["email"], first.email)
        self.assertEqual(browser.get("/api/me/wallet").json(), first_wallet)


if __name__ == "__main__":
    unittest.main()
