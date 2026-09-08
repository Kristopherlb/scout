#!/usr/bin/env python3
"""Direct unit coverage of lfd_common — the trust-boundary + gate module.
These exercise the helpers in-process (the pipeline hits them via
subprocess, which line coverage can't see) so the module the whole design
leans on stays measurably covered."""
import os
import shutil
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
import lfd_common  # noqa: E402


class TestRequiredConfig(unittest.TestCase):
    def test_value_requires_presence_and_nonempty_by_default(self):
        self.assertEqual(lfd_common.config_value({"KEY": "value"}, "KEY"), "value")
        with self.assertRaises(lfd_common.ConfigError):
            lfd_common.config_value({}, "KEY")
        with self.assertRaises(lfd_common.ConfigError):
            lfd_common.config_value({"KEY": ""}, "KEY")
        self.assertEqual(
            lfd_common.config_value({"KEY": ""}, "KEY", allow_empty=True), "")

    def test_integer_validation(self):
        self.assertEqual(lfd_common.config_int({"N": "3"}, "N", minimum=1), 3)
        with self.assertRaises(lfd_common.ConfigError):
            lfd_common.config_int({"N": "three"}, "N")
        with self.assertRaises(lfd_common.ConfigError):
            lfd_common.config_int({"N": "0"}, "N", minimum=1)

    def test_float_validation(self):
        self.assertEqual(
            lfd_common.config_float({"N": "0.5"}, "N", minimum=0, maximum=1),
            0.5)
        for invalid in ("not-a-number", "nan", "inf"):
            with self.subTest(invalid=invalid), self.assertRaises(lfd_common.ConfigError):
                lfd_common.config_float({"N": invalid}, "N")
        with self.assertRaises(lfd_common.ConfigError):
            lfd_common.config_float({"N": "-1"}, "N", minimum=0)
        with self.assertRaises(lfd_common.ConfigError):
            lfd_common.config_float({"N": "2"}, "N", maximum=1)


class TestLogIO(unittest.TestCase):
    def test_append_and_read_roundtrip(self):
        d = tempfile.mkdtemp()
        try:
            log = os.path.join(d, "log.jsonl")
            lfd_common.append_log_row(log, {"cycle": 1, "holdout_score": 0.5})
            lfd_common.append_log_row(log, {"cycle": 2, "holdout_score": 0.6})
            rows = lfd_common.read_log(log)
            self.assertEqual([r["cycle"] for r in rows], [1, 2])
        finally:
            shutil.rmtree(d)

    def test_read_missing_is_empty(self):
        self.assertEqual(lfd_common.read_log("/no/such/log.jsonl"), [])


class TestIterTargets(unittest.TestCase):
    def test_yields_only_dirs_with_config(self):
        hub = tempfile.mkdtemp()
        try:
            good = os.path.join(hub, "targets", "good")
            os.makedirs(good)
            with open(os.path.join(good, "config.env"), "w") as f:
                f.write('STATUS="active"\n')
            os.makedirs(os.path.join(hub, "targets", "no_config"))
            names = [n for n, _, _ in lfd_common.iter_targets(hub)]
            self.assertEqual(names, ["good"])
        finally:
            shutil.rmtree(hub)

    def test_missing_targets_dir_yields_nothing(self):
        hub = tempfile.mkdtemp()
        try:
            self.assertEqual(list(lfd_common.iter_targets(hub)), [])
        finally:
            shutil.rmtree(hub)


class TestActivationBlockers(unittest.TestCase):
    def test_non_active_never_blocked(self):
        self.assertEqual(
            lfd_common.activation_blockers({"STATUS": "onboarding"}, "/nope"), [])

    def test_active_facade_lists_all_three(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "harness"))
            blockers = lfd_common.activation_blockers(
                {"STATUS": "active", "BUILD_CMD": "", "HEALTH_CHECK": ""}, d)
            joined = " ".join(blockers).lower()
            self.assertIn("liveness", joined)
            self.assertIn("audit", joined)
            self.assertIn("calibration", joined)
        finally:
            shutil.rmtree(d)


class TestDivergenceGuards(unittest.TestCase):
    def test_none_values_do_not_flag(self):
        rows = [{"dev_ci": [None, 0.5], "holdout_score": 0.5} for _ in range(6)]
        self.assertFalse(lfd_common.check_divergence(rows, 5))

    def test_missing_holdout_key_does_not_crash(self):
        rows = [{"dev_ci": [0.5, 0.6]} for _ in range(6)]
        self.assertFalse(lfd_common.check_divergence(rows, 5))


class TestSparklineEdges(unittest.TestCase):
    def test_empty_and_all_none(self):
        self.assertEqual(lfd_common.sparkline([]), "")
        self.assertEqual(lfd_common.sparkline([None, None]), "")

    def test_flat_series_renders(self):
        out = lfd_common.sparkline([0.5, 0.5, 0.5])
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
