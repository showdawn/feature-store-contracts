import os
import tempfile
import unittest

import pandas as pd
import duckdb

import run
from fscontracts.generate import Params, generate


class RunnerTests(unittest.TestCase):
    def test_quick_default_is_separate_and_explicit_output_is_honored(self):
        self.assertTrue(callable(getattr(run, "output_directory", None)))
        self.assertEqual(run.output_directory(True), os.path.join(run.OUT, "quick"))
        self.assertEqual(run.output_directory(False), run.OUT)
        with tempfile.TemporaryDirectory() as destination:
            self.assertEqual(run.output_directory(True, destination), destination)

    def test_sweep_summary_reports_seed_mean_and_extremes(self):
        self.assertTrue(callable(getattr(run, "summarize_sweep", None)))
        raw = pd.DataFrame({"semantics": ["valid"] * 3, "seed": [7, 11, 19],
                            "correction_share": [.15] * 3,
                            "disagreement_rate": [.1, .2, .3]})
        result = run.summarize_sweep(raw, "correction_share").iloc[0]
        self.assertAlmostEqual(result.disagreement_rate_mean, .2)
        self.assertAlmostEqual(result.disagreement_rate_min, .1)
        self.assertAlmostEqual(result.disagreement_rate_max, .3)
        self.assertEqual(result.seeds, 3)

    def test_environment_reports_resources_without_host_or_workspace(self):
        self.assertTrue(callable(getattr(run, "environment_record", None)))
        with duckdb.connect(config={"threads": 2}) as con:
            result = run.environment_record(con, True, Params(n_orders=20), {}, .01)
        self.assertEqual(result["duckdb_threads"], 2)
        self.assertIn("python", result["versions"])
        self.assertIn("ram_bytes", result)
        self.assertIn("cpu_model", result)
        self.assertNotIn("hostname", result)
        self.assertNotIn("working_directory", result)

    def test_closed_api_comparison_executes_both_legitimate_interpretations(self):
        self.assertTrue(callable(getattr(run, "governed_comparison", None)))
        tables = generate(Params(n_orders=80))
        with duckdb.connect(config={"threads": 2}) as con:
            run.load(con, tables)
            comparison, receipts = run.governed_comparison(con, tables["facilities"])
        self.assertEqual(len(comparison), 7)
        self.assertEqual(comparison.executed.sum(), 2)
        known = comparison[comparison.variant.str.startswith("J5")].iloc[0]
        corrected = comparison[comparison.variant.str.startswith("J6")].iloc[0]
        self.assertEqual(known.disagreement_rate, 0)
        self.assertFalse(bool(corrected.interpretation_matches_question))
        self.assertEqual({r["interpretation"] for r in receipts}, {"as_known", "corrected"})

    def test_no_lag_control_has_equal_temporal_outputs(self):
        params = Params(n_orders=80, short_lag_share=0, late_arrival_share=0, correction_share=0)
        tables = generate(params)
        with duckdb.connect(config={"threads": 2}) as con:
            run.load(con, tables)
            result = run.three_reads(con, tables["facilities"])
        temporal = result[result.semantics.isin(["valid", "bitemporal"])]
        self.assertEqual(temporal.disagreement_rate.tolist(), [0, 0])


if __name__ == "__main__":
    unittest.main()
