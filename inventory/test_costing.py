from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .costing import CostBalance, CostMethod, allocate_landed_cost, consume_stock


D = Decimal


class CostingTests(SimpleTestCase):
    def test_fifo_uses_oldest_cost_then_leaves_unconsumed_layers(self):
        oldest = CostBalance(D("5"), D("50"))
        second = CostBalance(D("5"), D("80"))
        third = CostBalance(D("2"), D("90"))
        cost, remaining = consume_stock(CostMethod.FIFO, [oldest, second, third], D("6"))
        self.assertEqual(cost, D("66.00"))
        self.assertEqual(remaining, (CostBalance(D("4"), D("64")), third))

    def test_average_uses_total_value_over_total_quantity(self):
        balance = CostBalance(D("10"), D("130"))
        cost, remaining = consume_stock(CostMethod.AVERAGE, [balance], D("6"))
        self.assertEqual((cost, remaining), (D("78.00"), (CostBalance(D("4"), D("52")),)))

    def test_partial_issues_release_all_rounding_remainder_on_exhaustion(self):
        for method in CostMethod.values:
            with self.subTest(method=method):
                initial = CostBalance(D("3"), D("0.01"))
                cost_one, rest = consume_stock(method, [initial], D("1"))
                cost_two, rest = consume_stock(method, rest, D("1"))
                cost_last, closing = consume_stock(method, rest, D("1"))
                self.assertEqual(cost_one + cost_two + cost_last, initial.amount)
                self.assertEqual(closing, ())
        free_stock = CostBalance(D("2"), D("0"))
        self.assertEqual(consume_stock(CostMethod.FIFO, [free_stock], D("2")), (D("0"), ()))

    def test_landed_cost_sums_and_preserves_zero_and_tie_order(self):
        freight = allocate_landed_cost(D("31.00"), [D("10"), D("5"), D("5"), D("0")])
        self.assertEqual(freight, (D("15.50"), D("7.75"), D("7.75"), D("0")))
        packaging = allocate_landed_cost(D("0.02"), [D("1"), D("1"), D("1"), D("0")])
        self.assertEqual(packaging, (D("0.01"), D("0.01"), D("0"), D("0")))
        more = allocate_landed_cost(D("0.01"), [D("1"), D("2")])
        self.assertEqual(more, (D("0"), D("0.01")))

    def test_rejects_invalid_quantity_value_and_allocation(self):
        pool = [CostBalance(D("2"), D("5"))]
        for quantity in (D("0"), D("-1"), D("3"), D("1.0001"), D("NaN"), 1.0):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                consume_stock(CostMethod.FIFO, pool, quantity)
        with self.assertRaises(ValidationError):
            consume_stock(CostMethod.AVERAGE, pool * 2, D(1))
        with self.assertRaises(ValidationError):
            consume_stock("lifo", pool, D(1))
        for amount, weights in [(D("0.001"), [D(1)]), (D(1), []), (D(1), [D(0)]), (D(1), [D(-1)]), (D(1), [1.0])]:
            with self.subTest(amount=amount, weights=weights), self.assertRaises(ValidationError):
                allocate_landed_cost(amount, weights)
