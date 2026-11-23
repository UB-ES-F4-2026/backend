"""Estat de finançament d'una oportunitat (US05.1 i US05.2)."""
import unittest
from datetime import UTC, datetime, timedelta

from app.core.commitments import OpportunityNotFundable, ensure_in_funding
from app.core.funding import FundingStatus, funding_status
from app.model_registry import load_models
from app.models.opportunity import Opportunity, OpportunityStatus

# Instanciar `Opportunity` configura els mappers, que necessiten tots els models
# carregats: sense això el fitxer només passaria executat amb la resta de proves.
load_models()

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
TARGET_CENTS = 300_000_00


def opportunity(**changes) -> Opportunity:
    """Una oportunitat publicada i en finançament, sense desar-la a la base de dades."""
    values = {
        "id": 1,
        "status": OpportunityStatus.PUBLISHED,
        "target_amount_cents": TARGET_CENTS,
        "committed_cents": 185_500_00,
        "deadline": NOW + timedelta(days=30),
        "date_published": NOW - timedelta(days=10),
        "date_closed": None,
    }
    values.update(changes)
    return Opportunity(**values)


class FundingStatusTest(unittest.TestCase):
    def test_published_with_pending_capital_and_time_is_in_funding(self):
        self.assertEqual(funding_status(opportunity(), NOW), FundingStatus.IN_FUNDING)

    def test_reaching_the_target_is_funded(self):
        for committed_cents in (TARGET_CENTS, TARGET_CENTS + 1):
            with self.subTest(committed_cents=committed_cents):
                self.assertEqual(
                    funding_status(opportunity(committed_cents=committed_cents), NOW),
                    FundingStatus.FUNDED,
                )

    def test_one_cent_below_the_target_is_still_in_funding(self):
        self.assertEqual(
            funding_status(opportunity(committed_cents=TARGET_CENTS - 1), NOW),
            FundingStatus.IN_FUNDING,
        )

    def test_deadline_passed_without_reaching_the_target_is_expired(self):
        self.assertEqual(
            funding_status(opportunity(deadline=NOW - timedelta(seconds=1)), NOW),
            FundingStatus.EXPIRED,
        )

    def test_the_deadline_instant_itself_is_already_expired(self):
        # El mateix límit que el catàleg, que només mostra `deadline > now`.
        self.assertEqual(
            funding_status(opportunity(deadline=NOW), NOW), FundingStatus.EXPIRED
        )
        self.assertEqual(
            funding_status(opportunity(deadline=NOW + timedelta(microseconds=1)), NOW),
            FundingStatus.IN_FUNDING,
        )

    def test_a_funded_opportunity_stays_funded_after_the_deadline(self):
        funded_and_past_deadline = opportunity(
            committed_cents=TARGET_CENTS, deadline=NOW - timedelta(days=5)
        )
        self.assertEqual(funding_status(funded_and_past_deadline, NOW), FundingStatus.FUNDED)

    def test_an_early_closure_prevails_over_target_and_deadline(self):
        closed = {"status": OpportunityStatus.CLOSED, "date_closed": NOW - timedelta(days=1)}
        cases = {
            "amb capital pendent i termini": opportunity(**closed),
            "amb l'objectiu assolit": opportunity(committed_cents=TARGET_CENTS, **closed),
            "amb el termini vençut": opportunity(deadline=NOW - timedelta(days=5), **closed),
        }
        for name, closed_opportunity in cases.items():
            with self.subTest(name):
                self.assertEqual(funding_status(closed_opportunity, NOW), FundingStatus.CLOSED)

    def test_a_draft_is_pending_review_whatever_its_capital_and_deadline(self):
        cases = {
            "acabada de crear": opportunity(status=OpportunityStatus.DRAFT, date_published=None),
            "amb l'objectiu cobert per l'aportació inicial": opportunity(
                status=OpportunityStatus.DRAFT,
                date_published=None,
                committed_cents=TARGET_CENTS,
            ),
            "amb el termini vençut": opportunity(
                status=OpportunityStatus.DRAFT,
                date_published=None,
                deadline=NOW - timedelta(days=5),
            ),
        }
        for name, draft in cases.items():
            with self.subTest(name):
                self.assertEqual(funding_status(draft, NOW), FundingStatus.PENDING_REVIEW)

    def test_a_rejected_opportunity_is_rejected_whatever_its_capital_and_deadline(self):
        cases = {
            "sense publicar": opportunity(status=OpportunityStatus.REJECTED, date_published=None),
            "després d'haver estat publicada": opportunity(status=OpportunityStatus.REJECTED),
            "amb l'objectiu assolit": opportunity(
                status=OpportunityStatus.REJECTED, committed_cents=TARGET_CENTS
            ),
            "amb el termini vençut": opportunity(
                status=OpportunityStatus.REJECTED, deadline=NOW - timedelta(days=5)
            ),
        }
        for name, rejected in cases.items():
            with self.subTest(name):
                self.assertEqual(funding_status(rejected, NOW), FundingStatus.REJECTED)

    def test_only_in_funding_opportunities_accept_contributions(self):
        """`ensure_in_funding` i `funding_status` no es poden contradir."""
        closed = {"status": OpportunityStatus.CLOSED, "date_closed": NOW - timedelta(days=1)}
        cases = [
            opportunity(),
            opportunity(committed_cents=TARGET_CENTS),
            opportunity(deadline=NOW - timedelta(days=5)),
            opportunity(**closed),
            opportunity(status=OpportunityStatus.DRAFT, date_published=None),
            opportunity(status=OpportunityStatus.REJECTED, date_published=None),
        ]
        seen = set()
        for case in cases:
            status = funding_status(case, NOW)
            seen.add(status)
            with self.subTest(status=status):
                if status == FundingStatus.IN_FUNDING:
                    ensure_in_funding(case, NOW)
                else:
                    with self.assertRaises(OpportunityNotFundable):
                        ensure_in_funding(case, NOW)
        self.assertEqual(seen, set(FundingStatus))


if __name__ == "__main__":
    unittest.main()
