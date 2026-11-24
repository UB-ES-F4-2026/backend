"""Recorreguts dels diners d'un extrem a l'altre de l'API.

Ingrés signat de Stripe, compromís, cartera, «Mis inversiones», detall, catàleg i
«Mis oportunidades» han de donar les mateixes xifres. Tot l'estat neix de les rutes
reals (registre, sessió, creació amb imatge); només la publicació es fa per ORM.
"""
import unittest

from integration_support import (
    COMMITMENT_NOT_AVAILABLE,
    DETAIL_NOT_AVAILABLE,
    INSUFFICIENT_BALANCE,
    NOT_ACCEPTED,
    IntegrationTestCase,
    opportunity_body,
)


class MoneyJourneyTest(IntegrationTestCase):
    database_prefix = "money_journey_integration_test_"

    def setUp(self):
        super().setUp()
        self.promoter = self.new_actor(promoter=True)

    def wallet(self, actor) -> dict:
        response = actor.client.get("/api/me/wallet")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def my_commitments(self, actor) -> dict:
        response = actor.client.get("/api/me/commitments")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def my_opportunities(self) -> dict:
        response = self.promoter.client.get("/api/me/opportunities")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def public_detail(self, opportunity_id: int) -> dict:
        response = self.anonymous.get(f"/api/opportunities/{opportunity_id}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def catalog_item(self, opportunity_id: int) -> dict:
        catalog = self.anonymous.get("/api/opportunities").json()
        (item,) = [item for item in catalog if item["id"] == opportunity_id]
        return item

    def assert_committed_matches_the_commitments(self, opportunity_id: int, expected: int):
        """El capital de l'oportunitat és exactament la suma dels seus compromisos."""
        stored = self.commitments(opportunity_id=opportunity_id)
        self.assertEqual(sum(commitment.amount_cents for commitment in stored), expected)
        self.assertEqual(self.opportunity_committed(opportunity_id), expected)

    def test_deposit_commitment_and_every_view_agree(self):
        opportunity = self.create_opportunity(self.promoter, publish=True)
        opportunity_id = opportunity["id"]
        investor = self.new_actor()
        self.assertEqual(
            self.wallet(investor),
            {"available_cents": 0, "committed_cents": 0, "currency": "eur"},
        )

        self.deposit(investor.id, 60_000)
        self.assertEqual(
            self.wallet(investor),
            {"available_cents": 60_000, "committed_cents": 0, "currency": "eur"},
        )

        response = self.commit(investor, opportunity_id, 40_000)

        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        after = {"available_cents": 20_000, "committed_cents": 40_000, "currency": "eur"}
        self.assertEqual(result["wallet"], after)
        self.assertEqual(
            result["opportunity"],
            {"id": opportunity_id, "target_amount_cents": 100_000, "committed_cents": 40_000},
        )
        self.assertEqual(result["commitment"]["amount_cents"], 40_000)
        # Cartera de l'inversor.
        self.assertEqual(self.wallet(investor), after)
        self.assertEqual(self.balances(investor.id), (20_000, 40_000))
        # «Mis inversiones».
        mine = self.my_commitments(investor)
        self.assertEqual(
            mine["summary"],
            {"total_committed_cents": 40_000, "commitments_count": 1, "in_funding_count": 1},
        )
        (commitment,) = mine["commitments"]
        self.assertEqual(commitment["id"], result["commitment"]["id"])
        self.assertEqual(commitment["amount_cents"], 40_000)
        self.assertIsNone(commitment["estimated_equity"])
        self.assertEqual(
            {key: commitment["opportunity"][key] for key in (
                "id", "title", "type", "funding_status", "target_amount_cents",
                "committed_cents", "is_public",
            )},
            {
                "id": opportunity_id,
                "title": opportunity["title"],
                "type": "real_estate",
                "funding_status": "in_funding",
                "target_amount_cents": 100_000,
                "committed_cents": 40_000,
                "is_public": True,
            },
        )
        # Detall públic i catàleg.
        self.assertEqual(self.public_detail(opportunity_id)["committed_cents"], 40_000)
        self.assertEqual(self.catalog_item(opportunity_id)["committed_cents"], 40_000)
        # «Mis oportunidades» de l'entitat promotora.
        promoted = self.my_opportunities()
        self.assertEqual(
            promoted["summary"],
            {
                "committed_cents": 40_000,
                "published_count": 1,
                "in_funding_count": 1,
                "pending_review_count": 0,
            },
        )
        (item,) = promoted["opportunities"]
        self.assertEqual(
            {key: item[key] for key in (
                "id", "funding_status", "committed_cents", "investors_count", "is_public",
            )},
            {
                "id": opportunity_id,
                "funding_status": "in_funding",
                "committed_cents": 40_000,
                "investors_count": 1,
                "is_public": True,
            },
        )
        # Un compromís reserva saldo de l'inversor: no és cap ingrés per a l'entitat promotora.
        self.assertEqual(self.balances(self.promoter.id), (0, 0))
        self.assert_committed_matches_the_commitments(opportunity_id, 40_000)

    def test_funding_the_target_updates_investor_promoter_and_catalog(self):
        opportunity_id = self.create_opportunity(self.promoter, publish=True)["id"]
        first = self.new_actor(available_cents=40_000)
        second = self.new_actor(available_cents=65_000)
        self.assertEqual(self.commit(first, opportunity_id, 40_000).status_code, 201)
        self.assertIn(opportunity_id, self.catalog_ids())

        completed = self.commit(second, opportunity_id, 60_000)

        self.assertEqual(completed.status_code, 201, completed.text)
        self.assertEqual(completed.json()["opportunity"]["committed_cents"], 100_000)
        # Finançada: surt del catàleg, però qui hi ha invertit en conserva el detall.
        self.assertNotIn(opportunity_id, self.catalog_ids())
        detail = self.public_detail(opportunity_id)
        self.assertEqual(detail["committed_cents"], detail["target_amount_cents"])
        # L'estat canvia també per a qui havia invertit abans.
        mine = self.my_commitments(first)
        self.assertEqual(
            mine["summary"],
            {"total_committed_cents": 40_000, "commitments_count": 1, "in_funding_count": 0},
        )
        self.assertEqual(mine["commitments"][0]["opportunity"]["funding_status"], "funded")
        promoted = self.my_opportunities()
        self.assertEqual(
            promoted["summary"],
            {
                "committed_cents": 100_000,
                "published_count": 1,
                "in_funding_count": 0,
                "pending_review_count": 0,
            },
        )
        (item,) = promoted["opportunities"]
        self.assertEqual((item["funding_status"], item["investors_count"]), ("funded", 2))
        entities = self.anonymous.get("/api/promotingentity").json()
        (entity,) = [entity for entity in entities if entity["user_id"] == self.promoter.id]
        self.assertEqual(entity["published_projects_count"], 1)

        # Amb l'objectiu assolit ja no s'accepta cap més aportació, encara que hi hagi saldo.
        late = self.commit(second, opportunity_id, 5_000)

        self.assertEqual((late.status_code, late.json()), (409, NOT_ACCEPTED))
        self.assertEqual(self.balances(second.id), (5_000, 60_000))
        self.assert_committed_matches_the_commitments(opportunity_id, 100_000)

    def test_opportunity_with_initial_contribution_is_reserved_listed_and_hidden(self):
        self.deposit(self.promoter.id, 800_000)

        response = self.post_opportunity(
            self.promoter.client,
            opportunity_body(target_amount_cents=15_000_000, initial_contribution_cents=500_000),
        )

        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        opportunity_id = created["id"]
        self.assertEqual(created["committed_cents"], 500_000)
        self.assertIsNone(created["date_published"])
        reserved = {"available_cents": 300_000, "committed_cents": 500_000, "currency": "eur"}
        self.assertEqual(self.wallet(self.promoter), reserved)
        # L'aportació inicial és un compromís més de l'entitat, encara sense detall públic.
        mine = self.my_commitments(self.promoter)
        self.assertEqual(
            mine["summary"],
            {"total_committed_cents": 500_000, "commitments_count": 1, "in_funding_count": 0},
        )
        (commitment,) = mine["commitments"]
        self.assertEqual(commitment["amount_cents"], 500_000)
        self.assertEqual(
            {key: commitment["opportunity"][key] for key in (
                "id", "funding_status", "committed_cents", "is_public",
            )},
            {
                "id": opportunity_id,
                "funding_status": "pending_review",
                "committed_cents": 500_000,
                "is_public": False,
            },
        )
        # A «Mis oportunidades» es llista, però no compta com a publicada ni al capital.
        promoted = self.my_opportunities()
        self.assertEqual(
            promoted["summary"],
            {
                "committed_cents": 0,
                "published_count": 0,
                "in_funding_count": 0,
                "pending_review_count": 1,
            },
        )
        (item,) = promoted["opportunities"]
        self.assertEqual(
            {key: item[key] for key in (
                "id", "funding_status", "committed_cents", "investors_count",
                "date_published", "is_public",
            )},
            {
                "id": opportunity_id,
                "funding_status": "pending_review",
                "committed_cents": 500_000,
                "investors_count": 1,
                "date_published": None,
                "is_public": False,
            },
        )
        # Pendent de revisió: no existeix per al públic ni admet aportacions de ningú.
        self.assertNotIn(opportunity_id, self.catalog_ids())
        for client in (self.anonymous, self.promoter.client):
            detail = client.get(f"/api/opportunities/{opportunity_id}")
            self.assertEqual((detail.status_code, detail.json()), (404, DETAIL_NOT_AVAILABLE))
        outsider = self.new_actor(available_cents=10_000)
        for actor in (outsider, self.promoter):
            rejected = self.commit(actor, opportunity_id, 5_000)
            self.assertEqual(
                (rejected.status_code, rejected.json()), (404, COMMITMENT_NOT_AVAILABLE)
            )
        self.assertEqual(self.balances(outsider.id), (10_000, 0))
        # El saldo reservat tampoc es pot retirar mentre es revisa.
        withdrawal = self.withdraw(self.promoter, 300_001)
        self.assertEqual(
            (withdrawal.status_code, withdrawal.json()), (409, INSUFFICIENT_BALANCE)
        )
        self.assertEqual(self.balances(self.promoter.id), (300_000, 500_000))
        self.assert_committed_matches_the_commitments(opportunity_id, 500_000)

    def test_published_opportunity_counts_its_initial_contribution_everywhere(self):
        self.deposit(self.promoter.id, 800_000)
        opportunity_id = self.create_opportunity(
            self.promoter, target_amount_cents=15_000_000, initial_contribution_cents=500_000
        )["id"]

        self.publish(opportunity_id)

        self.assertEqual(self.catalog_item(opportunity_id)["committed_cents"], 500_000)
        self.assertEqual(self.public_detail(opportunity_id)["committed_cents"], 500_000)
        mine = self.my_commitments(self.promoter)
        self.assertEqual(mine["summary"]["in_funding_count"], 1)
        self.assertEqual(
            (
                mine["commitments"][0]["opportunity"]["funding_status"],
                mine["commitments"][0]["opportunity"]["is_public"],
            ),
            ("in_funding", True),
        )
        self.assertEqual(
            self.my_opportunities()["summary"],
            {
                "committed_cents": 500_000,
                "published_count": 1,
                "in_funding_count": 1,
                "pending_review_count": 0,
            },
        )

        # Un inversor i la mateixa entitat hi aporten: dos usuaris diferents, tres compromisos.
        investor = self.new_actor(available_cents=10_000)
        self.assertEqual(self.commit(investor, opportunity_id, 5_000).status_code, 201)
        self.assertEqual(self.commit(self.promoter, opportunity_id, 5_000).status_code, 201)

        (item,) = self.my_opportunities()["opportunities"]
        self.assertEqual((item["committed_cents"], item["investors_count"]), (510_000, 2))
        self.assertEqual(self.balances(self.promoter.id), (295_000, 505_000))
        self.assertEqual(self.balances(investor.id), (5_000, 5_000))
        self.assert_committed_matches_the_commitments(opportunity_id, 510_000)


if __name__ == "__main__":
    unittest.main()
