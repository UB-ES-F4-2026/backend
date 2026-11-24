"""Càlcul pur de la participació estimada d'una inversió empresarial (US03.1.2)."""
import unittest
from decimal import Decimal

from app.core.commitments import estimated_equity_percent


class EstimatedEquityCalculationTest(unittest.TestCase):
    def equity(self, amount_cents: int, valuation_cents: int, target_cents: int) -> Decimal:
        return estimated_equity_percent(
            amount_cents,
            pre_investment_valuation_cents=valuation_cents,
            target_amount_cents=target_cents,
        )

    def test_amount_over_pre_investment_valuation_plus_target(self):
        # La referència de la issue: 1.000 € sobre 2.700.000 € + 300.000 € és un 0,033 %.
        reference = self.equity(1_000_00, 2_700_000_00, 300_000_00)
        self.assertEqual(reference.quantize(Decimal("0.001")), Decimal("0.033"))
        self.assertEqual(self.equity(300_000_00, 2_700_000_00, 300_000_00), Decimal("10"))
        self.assertEqual(self.equity(50_000_00, 150_000_00, 50_000_00), Decimal("25"))

    def test_is_proportional_to_the_amount(self):
        single = self.equity(1_000_00, 2_700_000_00, 300_000_00)
        self.assertEqual(self.equity(3_000_00, 2_700_000_00, 300_000_00), Decimal("0.1"))
        self.assertLess(single, self.equity(1_000_01, 2_700_000_00, 300_000_00))

    def test_is_exact_to_the_cent(self):
        # Un cèntim sobre 3.000.000 €: sense arrodoniments intermedis.
        self.assertEqual(
            self.equity(1, 2_700_000_00, 300_000_00), Decimal(1) / Decimal(3_000_000)
        )


if __name__ == "__main__":
    unittest.main()
