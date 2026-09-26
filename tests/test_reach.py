"""Hand-calculated tests of the counterfactual deletion demonstration."""

import unittest

import duckdb

from fscontracts import reach


class ReachTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("""
            CREATE TABLE orders (
                order_id INTEGER, order_date DATE, region_id INTEGER,
                customer_id INTEGER, units INTEGER);
            INSERT INTO orders VALUES
              (1, '2024-01-01', 10, 1, 4),
              (2, '2024-01-02', 10, 2, 6),
              (3, '2024-01-08', 10, 2, 8),
              (4, '2024-01-09', 20, 3, 5),
              (5, '2024-01-15', 10, 3, 3),
              (6, '2024-01-10', 10, 4, 100);
            CREATE TABLE assignment (
                region_id INTEGER, valid_from DATE, recorded_at DATE,
                facility_id INTEGER);
            INSERT INTO assignment VALUES
              (10, '2024-01-01', '2024-01-01', 1),
              (20, '2024-01-01', '2024-01-01', 1);
            CREATE TABLE capacity (
                facility_id INTEGER, valid_from DATE, recorded_at DATE,
                capacity DOUBLE);
            INSERT INTO capacity VALUES (1, '2024-01-01', '2024-01-01', 100);
        """)

    def tearDown(self):
        self.con.close()

    def feature_values(self, table):
        return self.con.execute(
            f"SELECT order_id, previous_week_region_units FROM {table} ORDER BY order_id"
        ).fetchall()

    def test_previous_complete_week_excludes_current_week_future_orders(self):
        reach.build_store(self.con)
        columns = [c[0] for c in self.con.execute('DESCRIBE training_read').fetchall()]
        self.assertIn('previous_week_region_units', columns)
        self.assertEqual(self.feature_values('training_read'),
                         [(1, 0), (2, 0), (3, 10), (4, 0), (5, 108), (6, 10)])

    def test_recompute_changes_other_customers_and_preserves_unaffected_rows(self):
        store = reach.build_store(self.con)
        report = reach.reach_report(self.con, store, 1)
        columns = [c[0] for c in self.con.execute('DESCRIBE dataset_v1_minus').fetchall()]
        self.assertIn('previous_week_region_units', columns)
        self.assertEqual(self.feature_values('dataset_v1_minus'),
                         [(2, 0), (3, 6), (4, 0), (5, 108), (6, 6)])
        dataset = next(h for h in report['hops'] if h['artifact'] == 'dataset v1')
        self.assertEqual(dataset['direct_rows'], 1)
        self.assertEqual(dataset['check']['other_rows_changed'], 2)
        self.assertEqual(dataset['check']['unaffected_rows_changed'], 0)
        self.assertEqual(dataset['check']['subject_rows_after'], 0)
        self.assertTrue(dataset['check']['verified'])
        self.assertEqual(dataset['reached'], 3)

    def test_retained_originals_unchanged_and_action_is_hypothetical(self):
        store = reach.build_store(self.con)
        names = ['orders', 'assignment', 'capacity', 'region_week_demand',
                 'training_read', 'dataset_v1', 'dataset_v2', 'dataset_v3']
        before = {n: self.con.execute(f'SELECT * FROM {n} ORDER BY ALL').fetchall() for n in names}
        report = reach.reach_report(self.con, store, 1)
        after = {n: self.con.execute(f'SELECT * FROM {n} ORDER BY ALL').fetchall() for n in names}
        self.assertEqual(before, after)
        self.assertEqual(report.get('mode'), 'hypothetical_recomputation')
        self.assertTrue(report.get('retained_originals_unchanged'))
        self.assertNotIn('deleted directly', reach.render_markdown(report))

    def test_missing_base_input_fails_instead_of_filtering_cached_features(self):
        store = reach.build_store(self.con)
        self.con.execute('DROP TABLE capacity')
        with self.assertRaisesRegex(ValueError, 'capacity'):
            reach.reach_report(self.con, store, 1)

    def test_changed_retained_input_is_rejected(self):
        store = reach.build_store(self.con)
        self.con.execute('UPDATE capacity SET capacity = 999')
        with self.assertRaisesRegex(ValueError, 'capacity'):
            reach.reach_report(self.con, store, 1)

    def test_manifest_identifies_inputs_and_model_claims_do_not_certify_removal(self):
        store = reach.build_store(self.con)
        manifest = store['manifests']['v1']
        self.assertIn('input_fingerprints', manifest)
        self.assertEqual(set(manifest['input_fingerprints']), {'orders', 'assignment', 'capacity'})
        report = reach.reach_report(self.con, store, 1)
        for hop in report['hops']:
            for field in ('lineage', 'consumption', 'action', 'verification', 'removal_certification'):
                self.assertIn(field, hop)
        models = [h for h in report['hops'] if h['artifact'].startswith('model ')]
        self.assertTrue(models)
        for model in models:
            self.assertEqual(model['verification'], 'not_performed')
            self.assertEqual(model['removal_certification'], 'none')
        self.assertEqual(report['hops'][-1]['lineage'], 'unknown')

    def test_subject_only_aggregate_cell_disappears_and_dependents_get_zero(self):
        self.con.execute("""
            INSERT INTO assignment VALUES (30, '2024-01-01', '2024-01-01', 1);
            INSERT INTO orders VALUES
              (7, '2024-01-03', 30, 1, 2), (8, '2024-01-08', 30, 8, 9);
        """)
        store = reach.build_store(self.con)
        report = reach.reach_report(self.con, store, 1)
        aggregate = next(h for h in report['hops'] if h['artifact'] == 'region_week_demand')
        self.assertEqual(aggregate['check']['removed_cells'], 1)
        self.assertTrue(aggregate['check']['verified'])
        columns = [c[0] for c in self.con.execute('DESCRIBE dataset_v1_minus').fetchall()]
        self.assertIn('previous_week_region_units', columns)
        self.assertEqual(self.con.execute(
            'SELECT previous_week_region_units FROM dataset_v1_minus WHERE order_id = 8'
        ).fetchone()[0], 0)

    def test_indirect_reach_crosses_a_dataset_boundary_without_direct_subject_rows(self):
        self.con.execute("""
            DELETE FROM orders;
            INSERT INTO orders VALUES
              (1, '2024-06-24', 10, 1, 4), (2, '2024-07-01', 10, 2, 5);
        """)
        store = reach.build_store(self.con)
        report = reach.reach_report(self.con, store, 1)
        dataset = next(h for h in report['hops'] if h['artifact'] == 'dataset v2')
        self.assertEqual(dataset['direct_rows'], 0)
        self.assertEqual(dataset['indirect_rows'], 1)
        self.assertEqual(self.feature_values('dataset_v2_minus'), [(2, 0)])
        self.assertTrue(any(h['artifact'] == 'model m2' for h in report['hops']))


if __name__ == '__main__':
    unittest.main()
