#!/usr/bin/env python3
"""Coverage-variance instrument — detects the code-shaped lookup table.

A genuine solution executes different code paths for different holdout
cases; a dispatcher-to-lookup-table runs the same handful of lines for
everything. This is the code-shaped sibling of the compressibility lint
(which catches DATA lookup tables). Low variance across diverse inputs is
the signature.
"""
import json
import os
import subprocess
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "ops"))
import coverage_variance as cv  # noqa: E402


class TestVarianceScore(unittest.TestCase):
    def test_identical_paths_score_zero(self):
        # every case hit the same lines → lookup-table signature
        fps = [[1, 2, 3], [1, 2, 3], [1, 2, 3]]
        self.assertAlmostEqual(cv.variance_score(fps), 0.0)

    def test_disjoint_paths_score_one(self):
        fps = [[1, 2], [3, 4], [5, 6]]
        self.assertAlmostEqual(cv.variance_score(fps), 1.0)

    def test_partial_overlap_between(self):
        fps = [[1, 2, 3], [1, 2, 4], [1, 5, 6]]
        s = cv.variance_score(fps)
        self.assertGreater(s, 0.0)
        self.assertLess(s, 1.0)

    def test_single_case_is_unknown(self):
        self.assertIsNone(cv.variance_score([[1, 2, 3]]))
        self.assertIsNone(cv.variance_score([]))


class TestTracer(unittest.TestCase):
    def test_records_different_lines_for_different_branches(self):
        def branch(n):
            if n > 0:
                return "pos"
            else:
                return "neg"
        fp_pos = cv.trace_lines(lambda: branch(5))
        fp_neg = cv.trace_lines(lambda: branch(-5))
        self.assertNotEqual(fp_pos, fp_neg)
        self.assertTrue(fp_pos)  # something was recorded

    def test_lookup_table_traces_identically(self):
        table = {"a": 1, "b": 2, "c": 3}
        def dispatch(key):
            return table[key]  # same line for every key
        fps = [cv.trace_lines(lambda k=k: dispatch(k)) for k in "abc"]
        self.assertAlmostEqual(cv.variance_score(fps), 0.0)


class TestCLI(unittest.TestCase):
    def run_cli(self, payload):
        return subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "ops", "coverage_variance.py"),
             "variance", "--stdin"],
            input=json.dumps(payload), capture_output=True, text=True)

    def test_cli_scores_fingerprints(self):
        out = self.run_cli({"fingerprints": [[1, 2, 3], [1, 2, 3]]})
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout)
        self.assertAlmostEqual(result["coverage_variance"], 0.0)
        self.assertEqual(result["n_cases"], 2)

    def test_cli_flags_below_floor(self):
        out = subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "ops", "coverage_variance.py"),
             "variance", "--stdin", "--floor", "0.2"],
            input=json.dumps({"fingerprints": [[1], [1], [1]]}),
            capture_output=True, text=True)
        result = json.loads(out.stdout)
        self.assertTrue(result["below_floor"])


if __name__ == "__main__":
    unittest.main()
