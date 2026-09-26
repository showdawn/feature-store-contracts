import datetime as dt
import unittest

import pandas as pd

from fscontracts.reads import compare


class ReconstructionComparisonTests(unittest.TestCase):
    def setUp(self):
        self.facilities = pd.DataFrame({"facility_id": [1], "open_date": [dt.date(2024, 1, 1)]})

    def test_equal_nulls_are_equal_and_missing_value_differs_from_minus_one(self):
        read = pd.DataFrame({"order_id": [1, 2, 3], "facility_id": [None, 1, 1],
                             "capacity": [None, None, 10],
                             "order_date": [dt.date(2024, 1, 2)] * 3})
        truth = pd.DataFrame({"order_id": [1, 2, 3], "facility_id": [None, 1, 1],
                              "capacity": [None, -1, 10]})
        result = compare(read, truth, self.facilities)
        self.assertEqual(result["facility_mismatch_rate"], 0)
        self.assertAlmostEqual(result.get("disagreement_rate", -1), 1 / 3)

    def test_mismatched_order_sets_fail_instead_of_silently_dropping_rows(self):
        read = pd.DataFrame({"order_id": [1], "facility_id": [1], "capacity": [10],
                             "order_date": [dt.date(2024, 1, 2)]})
        truth = pd.DataFrame({"order_id": [1, 2], "facility_id": [1, 1], "capacity": [10, 10]})
        with self.assertRaises(ValueError):
            compare(read, truth, self.facilities)

    def test_missing_values_are_reported_without_a_fabricated_numeric_error(self):
        read = pd.DataFrame({"order_id": [1, 2, 3, 4], "facility_id": [1] * 4,
                             "capacity": [None, None, 20, 10],
                             "order_date": [dt.date(2024, 1, 2)] * 4})
        truth = pd.DataFrame({"order_id": [1, 2, 3, 4], "facility_id": [1] * 4,
                              "capacity": [10, None, None, 10]})
        self.assertEqual(compare(read, truth, self.facilities), {
            "rows": 4,
            "disagreement_rate": .5,
            "facility_mismatch_rate": 0,
            "impossible_rate": 0,
            "missing_rate": .5,
        })


if __name__ == "__main__":
    unittest.main()
