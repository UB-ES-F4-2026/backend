"""El saldo quan hi intervenen alhora ingressos, compromisos, retirades i creacions.

Cada mòdul ja prova el seu costat; aquí es comprova que cap combinació gasta dues
vegades el mateix saldo ni toca el saldo compromès (US03.1.1, US04.1, US04.3, US06.1.1).
"""
import unittest

from integration_support import (
    INSUFFICIENT_BALANCE,
    INSUFFICIENT_FUNDS,
    MASKED_IBAN,
    IntegrationTestCase,
    opportunity_body,
    payment_event,
)


class CommittedBalanceTest(IntegrationTestCase):
    """Un inversor amb 250,00 € que n'ha compromès 100,00 € en una oportunitat."""

    database_prefix = "wallet_flows_integration_test_"

    def setUp(self):
        super().setUp()
        promoter = self.new_actor(promoter=True)
        self.opportunity_id = self.create_opportunity(promoter, publish=True)["id"]
        self.investor = self.new_actor(available_cents=25_000)
        committed = self.commit(self.investor, self.opportunity_id, 10_000)
        self.assertEqual(committed.status_code, 201, committed.text)

    def assert_commitment_intact(self, available_cents: int):
        self.assertEqual(self.balances(self.investor.id), (available_cents, 10_000))
        stored = self.commitments(user_id=self.investor.id)
        self.assertEqual([commitment.amount_cents for commitment in stored], [10_000])
        self.assertEqual(self.opportunity_committed(self.opportunity_id), 10_000)

    def test_withdrawal_cannot_use_committed_balance(self):
        # 15.001 supera el disponible per un cèntim; 25.000 és disponible més compromès.
        for amount_cents in (15_001, 25_000):
            with self.subTest(amount_cents=amount_cents):
                response = self.withdraw(self.investor, amount_cents)

                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), INSUFFICIENT_BALANCE)
                self.assert_commitment_intact(available_cents=15_000)

        wallet = self.investor.client.get("/api/me/wallet")
        self.assertEqual(
            wallet.json(),
            {"available_cents": 15_000, "committed_cents": 10_000, "currency": "eur"},
        )

    def test_withdrawing_all_available_leaves_the_commitment_reserved(self):
        response = self.withdraw(self.investor, 15_000)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "amount_cents": 15_000,
                "masked_iban": MASKED_IBAN,
                "account_holder": "Ada Lovelace",
                "available_cents": 0,
                "currency": "eur",
            },
        )
        self.assert_commitment_intact(available_cents=0)
        wallet = self.investor.client.get("/api/me/wallet")
        self.assertEqual(
            wallet.json(),
            {"available_cents": 0, "committed_cents": 10_000, "currency": "eur"},
        )
        listed = self.investor.client.get("/api/me/commitments").json()
        self.assertEqual(listed["summary"]["total_committed_cents"], 10_000)

        # Sense disponible no es pot comprometre res més, encara que hi hagi saldo compromès.
        another = self.commit(self.investor, self.opportunity_id, 5_000)

        self.assertEqual(another.status_code, 409)
        self.assertEqual(another.json(), INSUFFICIENT_FUNDS)
        self.assert_commitment_intact(available_cents=0)


class WalletConcurrencyTest(IntegrationTestCase):
    """Operacions de mòduls diferents que competeixen pel mateix wallet."""

    database_prefix = "wallet_concurrency_integration_test_"

    def test_commitments_and_withdrawals_racing_never_overspend(self):
        promoter = self.new_actor(promoter=True)
        opportunities = [
            self.create_opportunity(promoter, publish=True, minimum_contribution_cents=1_000)["id"]
            for _ in range(4)
        ]
        investor = self.new_actor(available_cents=10_000)
        commits = [
            lambda client, opportunity_id=opportunity_id: self.commit(
                investor, opportunity_id, 3_000, client
            )
            for opportunity_id in opportunities
        ]
        withdrawals = [lambda client: self.withdraw(investor, 3_000, client)] * 4

        responses = self.simultaneous(
            commits + withdrawals, queued_behind_wallet_of=investor.id
        )

        commit_responses, withdrawal_responses = responses[:4], responses[4:]
        accepted_commits = [r for r in commit_responses if r.status_code == 201]
        accepted_withdrawals = [r for r in withdrawal_responses if r.status_code == 200]
        # Amb 100,00 € només hi caben tres operacions de 30,00 €, siguin del tipus que siguin.
        self.assertEqual(len(accepted_commits) + len(accepted_withdrawals), 3)
        for response in commit_responses:
            if response.status_code != 201:
                self.assertEqual((response.status_code, response.json()), (409, INSUFFICIENT_FUNDS))
        for response in withdrawal_responses:
            if response.status_code != 200:
                self.assertEqual(
                    (response.status_code, response.json()), (409, INSUFFICIENT_BALANCE)
                )
        committed_cents = 3_000 * len(accepted_commits)
        self.assertEqual(self.balances(investor.id), (1_000, committed_cents))
        stored = self.commitments(user_id=investor.id)
        self.assertEqual(sum(commitment.amount_cents for commitment in stored), committed_cents)
        self.assertEqual(len(stored), len(accepted_commits))
        for opportunity_id, response in zip(opportunities, commit_responses):
            expected = 3_000 if response.status_code == 201 else 0
            self.assertEqual(self.opportunity_committed(opportunity_id), expected)

    def test_deposit_arriving_during_a_commitment_is_not_lost(self):
        promoter = self.new_actor(promoter=True)
        opportunity_id = self.create_opportunity(promoter, publish=True)["id"]
        investor = self.new_actor(available_cents=10_000)
        event = payment_event(investor.id, 5_000)

        deposited, committed = self.simultaneous(
            [
                lambda client: self.post_event(event, client=client),
                lambda client: self.commit(investor, opportunity_id, 10_000, client),
            ],
            queued_behind_wallet_of=investor.id,
        )

        # Passi qui passi primer, les dues operacions hi caben i cap trepitja l'altra.
        self.assertEqual((deposited.status_code, deposited.json()), (200, {"status": "success"}))
        self.assertEqual(committed.status_code, 201, committed.text)
        self.assertEqual(self.balances(investor.id), (5_000, 10_000))
        self.assertEqual(len(self.deposits(investor.id)), 2)
        self.assertEqual(self.opportunity_committed(opportunity_id), 10_000)

    def test_deposit_arriving_during_a_withdrawal_is_not_lost(self):
        investor = self.new_actor(available_cents=10_000)
        event = payment_event(investor.id, 5_000)

        deposited, withdrawn = self.simultaneous(
            [
                lambda client: self.post_event(event, client=client),
                lambda client: self.withdraw(investor, 10_000, client),
            ],
            queued_behind_wallet_of=investor.id,
        )

        self.assertEqual((deposited.status_code, deposited.json()), (200, {"status": "success"}))
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        self.assertEqual(self.balances(investor.id), (5_000, 0))
        self.assertEqual(len(self.deposits(investor.id)), 2)

    def test_simultaneous_creations_cannot_reserve_the_same_balance(self):
        # Doble enviament de «Enviar a revisión» amb una aportació inicial de 5.000,00 €.
        promoter = self.new_actor(promoter=True, available_cents=800_000)
        body = opportunity_body(
            target_amount_cents=15_000_000, initial_contribution_cents=500_000
        )

        responses = self.simultaneous(
            [
                lambda client: self.post_opportunity(client, body, headers=promoter.headers)
            ]
            * 2,
            queued_behind_wallet_of=promoter.id,
        )

        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        created = next(r.json() for r in responses if r.status_code == 201)
        rejected = next(r.json() for r in responses if r.status_code == 409)
        self.assertEqual(rejected, INSUFFICIENT_BALANCE)
        self.assertEqual(created["committed_cents"], 500_000)
        self.assertEqual(self.balances(promoter.id), (300_000, 500_000))
        # De la creació rebutjada no en queda ni l'oportunitat, ni el compromís, ni cap fitxer.
        (stored,) = self.opportunities_of(promoter.id)
        self.assertEqual((stored.id, stored.committed_cents), (created["id"], 500_000))
        (commitment,) = self.commitments(user_id=promoter.id)
        self.assertEqual(
            (commitment.opportunity_id, commitment.amount_cents), (created["id"], 500_000)
        )
        files = self.stored_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(
            [path.parent.as_posix() for path in files], [f"opportunities/{created['id']}"]
        )


if __name__ == "__main__":
    unittest.main()
