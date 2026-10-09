import unittest

from ix_crate.batch_notify import estimate_minutes


class EstimateMinutesTests(unittest.TestCase):
    def test_stemit_zero_hygiene_band(self):
        lo, hi = estimate_minutes(budget=0, hygiene=True, follow=False)
        self.assertLessEqual(lo, hi)
        self.assertGreaterEqual(lo, 15)

    def test_stem_budget_widens(self):
        lo0, _ = estimate_minutes(budget=0)
        lo100, hi100 = estimate_minutes(budget=100)
        self.assertGreater(lo100, lo0)
        self.assertGreater(hi100, 300)

    def test_batches_sum(self):
        lo, hi = estimate_minutes(batches=[50, 50])
        lo_one, hi_one = estimate_minutes(budget=100)
        self.assertEqual(lo, lo_one)
        self.assertEqual(hi, hi_one)


if __name__ == "__main__":
    unittest.main()
