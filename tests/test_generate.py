import dataclasses
import unittest

import pandas as pd

from fscontracts.generate import Params, generate


class ControlledWorldTests(unittest.TestCase):
    def test_overlays_preserve_all_base_world_values(self):
        p = Params(n_orders=80)
        plain = generate(dataclasses.replace(p, short_lag_share=0, late_arrival_share=0,
                                             correction_share=0))
        overlaid = generate(dataclasses.replace(p, late_arrival_share=.3, correction_share=.5))
        for name in ("orders", "facilities"):
            with self.subTest(table=name):
                pd.testing.assert_frame_equal(plain[name], overlaid[name])
        for name, key in (("capacity", "facility_id"), ("assignment", "region_id")):
            columns = [c for c in plain[name] if c not in ("recorded_at", "is_correction")]
            left = plain[name][columns].sort_values([key, "valid_from"]).reset_index(drop=True)
            right = overlaid[name].loc[~overlaid[name].is_correction, columns]
            right = right.sort_values([key, "valid_from"]).reset_index(drop=True)
            with self.subTest(table=name):
                pd.testing.assert_frame_equal(left, right)

    def test_increasing_correction_share_preserves_existing_candidates(self):
        p = Params(n_orders=10, correction_share=.15)
        low = generate(p)
        high = generate(dataclasses.replace(p, correction_share=.5))
        for name, key, value in (("capacity", "facility_id", "capacity"),
                                 ("assignment", "region_id", "facility_id")):
            a = low[name].loc[low[name].is_correction]
            b = high[name].loc[high[name].is_correction]
            common = a.merge(b, on=[key, "valid_from"], suffixes=("_low", "_high"))
            self.assertGreater(len(a), 0)
            self.assertEqual(len(common), len(a))
            self.assertTrue((common[value + "_low"] == common[value + "_high"]).all())
            self.assertTrue((common.recorded_at_low == common.recorded_at_high).all())

    def test_correction_overlay_does_not_move_base_recording_times(self):
        p = Params(n_orders=10, correction_share=0)
        low = generate(p)
        high = generate(dataclasses.replace(p, correction_share=.5))
        for name in ("capacity", "assignment"):
            pd.testing.assert_frame_equal(low[name], high[name].loc[~high[name].is_correction]
                                          .reset_index(drop=True))


if __name__ == "__main__":
    unittest.main()
