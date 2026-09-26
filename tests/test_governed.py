import hashlib
import json
import unittest

import duckdb
import pandas as pd

from fscontracts import governed


class GovernedTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        # Hand-checkable fixture: inclusive day-2 assignment, later correction,
        # and a day-3 reassignment that was not recorded until day 4.
        self.con.execute("""
            CREATE TABLE orders(order_id INTEGER, order_date DATE, region_id INTEGER,
                                customer_id INTEGER, units INTEGER);
            INSERT INTO orders VALUES (0, '2023-12-31', 1, 7, 1),
              (1, '2024-01-01', 1, 7, 2), (2, '2024-01-02', 1, 8, 3),
              (3, '2024-01-03', 1, 9, 4);
            CREATE TABLE assignment(region_id INTEGER, facility_id INTEGER,
                                    valid_from DATE, recorded_at DATE);
            INSERT INTO assignment VALUES (1, 10, '2024-01-01', '2024-01-01'),
              (1, 20, '2024-01-02', '2024-01-02'),
              (1, 30, '2024-01-03', '2024-01-04');
            CREATE TABLE capacity(facility_id INTEGER, capacity DOUBLE,
                                  valid_from DATE, recorded_at DATE);
            INSERT INTO capacity VALUES (10, 100, '2024-01-01', '2024-01-01'),
              (20, 200, '2024-01-02', '2024-01-02'),
              (20, 250, '2024-01-02', '2024-01-04'),
              (30, 300, '2024-01-03', '2024-01-04');
        """)

    def execute(self, **kwargs):
        return governed.execute_contract(self.con, **kwargs)

    def test_as_known_includes_equal_boundaries_and_excludes_later_knowledge(self):
        result, _ = self.execute()
        self.assertEqual(result.order_id.tolist(), [0, 1, 2, 3])
        self.assertTrue(pd.isna(result.iloc[0].facility_id))
        self.assertTrue(pd.isna(result.iloc[0].capacity))
        self.assertEqual(result.facility_id.iloc[1:].tolist(), [10, 20, 20])
        self.assertEqual(result.capacity.iloc[1:].tolist(), [100, 200, 200])

    def test_corrected_is_a_distinct_legitimate_interpretation(self):
        result, receipt = self.execute(interpretation="corrected")
        self.assertEqual(result.facility_id.iloc[1:].tolist(), [10, 20, 30])
        self.assertEqual(result.capacity.iloc[1:].tolist(), [100, 250, 300])
        self.assertEqual(receipt["knowledge_cutoff"], "all_recorded_rows_in_input_snapshot")

    def test_bad_public_choices_are_rejected(self):
        for kwargs in ({"interpretation": "valid"}, {"interpretation": None},
                       {"interpretation": ["as_known"]}, {"feature_version": "capacity_v2"},
                       {"backend": "spark"}, {"backend": 1}, {"cutoff": "now"},
                       {"cutoff": "order_date; DROP TABLE orders"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.execute(**kwargs)

    def test_caller_cannot_supply_sql_or_change_either_join(self):
        for kwargs in ({"sql": "SELECT 1"}, {"valid_op": "<"},
                       {"assignment_semantics": "current"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(TypeError):
                self.execute(**kwargs)
        self.assertEqual(self.con.execute("SELECT count(*) FROM orders").fetchone()[0], 4)

    def test_missing_timestamp_column_is_rejected(self):
        self.con.execute("ALTER TABLE capacity DROP COLUMN recorded_at")
        with self.assertRaisesRegex(ValueError, "capacity.*recorded_at"):
            self.execute()

    def test_text_timestamp_is_rejected_instead_of_implicitly_cast(self):
        self.con.execute("ALTER TABLE assignment ALTER valid_from TYPE VARCHAR")
        with self.assertRaisesRegex(ValueError, "assignment.*valid_from"):
            self.execute()

    def test_missing_table_is_rejected(self):
        self.con.execute("DROP TABLE assignment")
        with self.assertRaisesRegex(ValueError, "assignment"):
            self.execute()

    def test_null_time_or_duplicate_temporal_key_is_rejected(self):
        self.con.execute("UPDATE capacity SET recorded_at = NULL WHERE facility_id = 10")
        with self.assertRaisesRegex(ValueError, "capacity.*NULL"):
            self.execute()
        self.con.execute("UPDATE capacity SET recorded_at = valid_from WHERE recorded_at IS NULL")
        self.con.execute("INSERT INTO assignment SELECT * FROM assignment LIMIT 1")
        with self.assertRaisesRegex(ValueError, "assignment.*duplicate"):
            self.execute()

    def test_duplicate_order_id_is_rejected(self):
        self.con.execute("INSERT INTO orders SELECT * FROM orders LIMIT 1")
        with self.assertRaisesRegex(ValueError, "orders.*duplicate"):
            self.execute()

    def test_receipt_binds_execution_and_source_content(self):
        _, receipt = self.execute()
        self.assertEqual(receipt["contract_version"], "capacity_v1")
        self.assertEqual(receipt["interpretation"], "as_known")
        self.assertEqual(receipt["valid_comparator"], "<=")
        self.assertEqual(receipt["cutoff"], "order_date")
        self.assertEqual(receipt["knowledge_cutoff"], "order_date")
        self.assertEqual(receipt["backend"], "duckdb")
        self.assertEqual(set(receipt["sources"]), {"orders", "assignment", "capacity"})
        for source in receipt["sources"].values():
            self.assertTrue(source["source_id"])
            self.assertEqual(len(source["sha256"]), 64)
            self.assertGreater(source["row_count"], 0)
            self.assertTrue(source["schema"])
        self.assertEqual(len(receipt["sql_sha256"]), 64)
        self.assertTrue(receipt["scope"])
        self.assertTrue(receipt["limitations"])
        json.dumps(receipt, allow_nan=False)
        _, corrected = self.execute(interpretation="corrected")
        self.assertNotEqual(receipt["sql_sha256"], corrected["sql_sha256"])
        self.assertEqual(receipt["sources"], corrected["sources"])
        self.con.execute("UPDATE capacity SET capacity = capacity + 1 WHERE facility_id = 10")
        _, changed = self.execute()
        self.assertNotEqual(receipt["sources"]["capacity"]["sha256"],
                            changed["sources"]["capacity"]["sha256"])
        self.assertEqual(receipt["sources"]["orders"], changed["sources"]["orders"])

    def test_fingerprint_is_stable_across_physical_row_order(self):
        _, first = self.execute()
        self.con.execute("CREATE OR REPLACE TABLE capacity AS SELECT * FROM capacity ORDER BY facility_id DESC, capacity DESC")
        _, reordered = self.execute()
        self.assertEqual(first["sources"]["capacity"], reordered["sources"]["capacity"])

    def test_capacity_fingerprint_matches_independent_canonical_bytes(self):
        # Literal schema/rows derived directly from the fixture, without calling
        # the encoder or SQL builder under test.
        canonical = (
            '[["capacity","DOUBLE"],["facility_id","INTEGER"],["recorded_at","DATE"],["valid_from","DATE"]]\n'
            '["100.0","10","2024-01-01","2024-01-01"]\n'
            '["200.0","20","2024-01-02","2024-01-02"]\n'
            '["250.0","20","2024-01-04","2024-01-02"]\n'
            '["300.0","30","2024-01-04","2024-01-03"]\n'
        )
        _, receipt = self.execute()
        self.assertEqual(receipt["sources"]["capacity"]["sha256"],
                         hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    def test_existing_transaction_is_not_committed_or_rolled_back(self):
        self.con.execute("BEGIN TRANSACTION")
        self.con.execute("UPDATE capacity SET capacity = 999 WHERE facility_id = 10")
        with self.assertRaisesRegex(ValueError, "active transaction"):
            self.execute()
        self.assertEqual(self.con.execute("SELECT capacity FROM capacity WHERE facility_id = 10").fetchone()[0], 999)
        self.con.execute("ROLLBACK")
        self.assertEqual(self.con.execute("SELECT capacity FROM capacity WHERE facility_id = 10").fetchone()[0], 100)

    def test_wrong_connection_object_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DuckDBPyConnection"):
            governed.execute_contract(None)

    def test_views_are_outside_supported_snapshot_scope(self):
        self.con.execute("ALTER TABLE capacity RENAME TO hidden_capacity")
        self.con.execute("CREATE VIEW capacity AS SELECT * FROM hidden_capacity")
        with self.assertRaisesRegex(ValueError, "capacity.*table"):
            self.execute()


if __name__ == "__main__":
    unittest.main()
