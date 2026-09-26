import dataclasses
import unittest

import numpy as np

from fscontracts.admission import admission_check, variants


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.valid = variants()[4]

    def assertRejected(self, job):
        decision, reason = admission_check(job)
        self.assertEqual(decision, "rejected")
        self.assertTrue(reason)

    def test_documented_variants_keep_their_declaration_outcomes(self):
        self.assertEqual([admission_check(j)[0] for j in variants()],
                         ["rejected", "rejected", "rejected", "admitted",
                          "admitted", "admitted", "rejected"])

    def test_unknown_interpretations_fail_closed(self):
        for value in ("", "historical", None, 1, ["as_known"], np.array(["as_known", "corrected"])):
            with self.subTest(value=value):
                self.assertRejected(dataclasses.replace(self.valid, interpretation=value))

    def test_both_builtin_dependencies_must_appear_once(self):
        a, c = self.valid.joins
        for joins in ((), (a,), (c,), (a, a), (a, c, c),
                      (a, c, dataclasses.replace(c, dimension="unknown"))):
            with self.subTest(joins=joins):
                self.assertRejected(dataclasses.replace(self.valid, joins=joins))

    def test_malformed_declaration_types_are_rejected(self):
        for job in (None, {}, dataclasses.replace(self.valid, joins=None),
                    dataclasses.replace(self.valid, joins=list(self.valid.joins)),
                    dataclasses.replace(self.valid, joins=("assignment", "capacity")),
                    dataclasses.replace(self.valid, sql=None)):
            with self.subTest(job=job):
                self.assertRejected(job)

    def test_predicates_must_be_boolean_and_cutoff_must_be_known(self):
        a, c = self.valid.joins
        bad_joins = [dataclasses.replace(a, valid_time_predicate=v)
                     for v in (1, "yes", None)]
        bad_joins += [dataclasses.replace(a, knowledge_time_predicate=v)
                      for v in (1, "yes", None)]
        bad_joins += [dataclasses.replace(a, knowledge_cutoff=v)
                      for v in ("later", None, 1, ["label"])]
        bad_joins += [dataclasses.replace(a, dimension=None)]
        for bad in bad_joins:
            with self.subTest(join=bad):
                self.assertRejected(dataclasses.replace(self.valid, joins=(bad, c)))

    def test_corrected_is_legitimate_with_a_snapshot_cutoff(self):
        for cutoff in ("now", "job_run"):
            job = dataclasses.replace(self.valid, interpretation="corrected",
                                      joins=tuple(dataclasses.replace(j, knowledge_cutoff=cutoff)
                                                  for j in self.valid.joins))
            self.assertEqual(admission_check(job)[0], "admitted")
        wrong = dataclasses.replace(self.valid, interpretation="corrected")
        self.assertRejected(wrong)


if __name__ == "__main__":
    unittest.main()
