#!/usr/bin/env python3
"""Hub test suite — stdlib unittest only. Run: bin/lfd test"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
import lfd_common  # noqa: E402

LOG_UTILS = os.path.join(HUB_ROOT, "ops", "log_utils.py")
POST_STATUS = os.path.join(HUB_ROOT, "ops", "post-status.sh")


def make_rows(dev_lower, holdout):
    return [{"cycle": i + 1, "dev_ci": [dl, dl + 0.06], "dev_score": dl + 0.03,
             "holdout_score": h, "holdout_ci": [h - 0.04, h + 0.04]}
            for i, (dl, h) in enumerate(zip(dev_lower, holdout))]


class TestDivergence(unittest.TestCase):
    def test_flags_reward_hacking(self):
        rows = make_rows([0.50, 0.55, 0.60, 0.65, 0.70],
                         [0.60, 0.61, 0.60, 0.60, 0.60])
        self.assertTrue(lfd_common.check_divergence(rows, 5))

    def test_healthy_run_not_flagged(self):
        rows = make_rows([0.50, 0.55, 0.60, 0.65, 0.70],
                         [0.50, 0.56, 0.61, 0.67, 0.72])
        self.assertFalse(lfd_common.check_divergence(rows, 5))

    def test_short_history_not_flagged(self):
        rows = make_rows([0.5, 0.6], [0.5, 0.5])
        self.assertFalse(lfd_common.check_divergence(rows, 5))

    def test_malformed_rows_not_flagged(self):
        rows = [{"cycle": i} for i in range(6)]
        self.assertFalse(lfd_common.check_divergence(rows, 5))


class TestValidation(unittest.TestCase):
    def test_floats(self):
        self.assertEqual(lfd_common.validate_float("0.5"), 0.5)
        for bad in ("nan", "inf", "-inf", "1e400", "abc", None, "", "1;rm -rf /"):
            self.assertIsNone(lfd_common.validate_float(bad), bad)

    def test_model_id(self):
        self.assertEqual(lfd_common.validate_model_id("executor-model-v1"),
                         "executor-model-v1")
        for bad in ("a b", "x" * 200, "`id`", "$(id)", 42, None, "a\nb"):
            self.assertIsNone(lfd_common.validate_model_id(bad), bad)


class TestTagMessageInjection(unittest.TestCase):
    """The fix for the tag-message injection: hostile content in, nulls out."""

    HOSTILE = [
        '{"dev_score": "__import__(\'os\').system(\'id\')", "dev_ci": [0, 1]}',
        '{"dev_score": 0.5, "dev_ci": ["$(touch /tmp/pwn)", 1]}',
        "'; touch /tmp/pwn; '",
        '{"model_id": "x; rm -rf ~", "dev_score": 0.5}',
        "not json at all",
        '[]', '5', '"str"',
    ]

    def parse(self, raw):
        out = subprocess.run([sys.executable, LOG_UTILS, "parse-tag-msg"],
                             input=raw, capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_hostile_messages_neutralized(self):
        for raw in self.HOSTILE:
            parsed = self.parse(raw)
            for field in lfd_common.AGENT_NUMERIC_FIELDS:
                self.assertIn(parsed[field], (None,) if field != "dev_score"
                              else (None, 0.5), f"{field} in {raw!r}")
            self.assertIsNone(parsed["model_id"] if "model_id" in raw else None)

    def test_valid_message_passes(self):
        parsed = self.parse(json.dumps({
            "dev_score": 0.61, "dev_ci": [0.58, 0.64],
            "model_id": "executor-model-v1", "reported_cost_usd": 1.5}))
        self.assertEqual(parsed["dev_score"], 0.61)
        self.assertEqual(parsed["dev_ci"], [0.58, 0.64])
        self.assertEqual(parsed["model_id"], "executor-model-v1")
        self.assertEqual(parsed["reported_cost_usd"], 1.5)


class TestLogAppend(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "harness"))
        with open(os.path.join(self.dir, "harness", "score-holdout.sh"), "w") as f:
            f.write("#!/bin/sh\n")
        self.log = os.path.join(self.dir, "log.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def append(self, **kw):
        args = [sys.executable, LOG_UTILS, "append", "--log", self.log,
                "--target-dir", self.dir, "--tag", kw.pop("tag", "holdout-check-1"),
                "--request-id", kw.pop("request_id", "0" * 32),
                "--sha", "abc123", "--holdout-score", kw.pop("score", "0.5"),
                "--ci-low", "0.45", "--ci-high", "0.55"]
        for k, v in kw.items():
            args += [f"--{k.replace('_', '-')}", v]
        return subprocess.run(args, capture_output=True, text=True)

    def test_append_and_dedup(self):
        self.assertEqual(self.append().returncode, 0)
        rows = lfd_common.read_log(self.log)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["holdout_score"], 0.5)
        self.assertIn("harness_version", rows[0])
        out = subprocess.run([sys.executable, LOG_UTILS, "has-tag", "--log",
                              self.log, "--tag", "holdout-check-1"],
                             capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "true")
        by_request = subprocess.run(
            [sys.executable, LOG_UTILS, "has-request", "--log", self.log,
             "--request-id", "0" * 32, "--sha", "abc123"],
            capture_output=True, text=True, check=True)
        self.assertEqual(by_request.stdout.strip(), "true")

    def test_rejects_non_numeric_score(self):
        res = self.append(score="__import__('os')")
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(lfd_common.read_log(self.log), [])

    def test_rejects_out_of_range_or_misordered_holdout_result(self):
        for arguments in (
                {"score": "1.1"},
                {"score": "0.5", "ci_low": "0.6", "ci_high": "0.8"}):
            with self.subTest(arguments=arguments):
                args = [sys.executable, LOG_UTILS, "append", "--log", self.log,
                        "--target-dir", self.dir, "--tag", "holdout-check-1",
                        "--request-id", "0" * 32, "--sha", "abc123",
                        "--holdout-score", arguments.get("score", "0.5"),
                        "--ci-low", arguments.get("ci_low", "0.45"),
                        "--ci-high", arguments.get("ci_high", "0.55")]
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(lfd_common.read_log(self.log), [])

    def test_rejects_malformed_private_detector_output(self):
        for field, value in (("probe_json", '{"operators":{"x":2}}'),
                             ("coverage_variance", "2")):
            with self.subTest(field=field):
                result = self.append(**{field: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(lfd_common.read_log(self.log), [])

    def test_hostile_agent_fields_stored_as_null(self):
        res = self.append(agent_fields='{"dev_score": "$(id)", "model_id": "a b c"}')
        self.assertEqual(res.returncode, 0, res.stderr)
        row = lfd_common.read_log(self.log)[0]
        self.assertIsNone(row["dev_score"])
        self.assertIsNone(row["model_id"])


class TestStatusAndDashboard(unittest.TestCase):
    def test_status_renders_example_with_flags(self):
        out = subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "tools", "lfd_status.py"),
             "--hub-root", HUB_ROOT, "--target", "_example"],
            capture_output=True, text=True, check=True).stdout
        self.assertIn("DIVERGENCE", out)
        self.assertIn("entity_swap", out)
        self.assertIn("BELOW FLOOR", out)

    def test_dashboard_emits_valid_html(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, "index.html")
            subprocess.run(
                [sys.executable, os.path.join(HUB_ROOT, "tools", "lfd_dashboard.py"),
                 "--hub-root", HUB_ROOT, "--out", out_path],
                capture_output=True, text=True, check=True)
            with open(out_path) as rendered:
                html = rendered.read()
        self.assertIn("<title>LFD Eval Hub</title>", html)
        start = html.index('type="application/json">') + len('type="application/json">')
        end = html.index("</script>", start)
        data = json.loads(html[start:end].replace("<\\/", "</"))
        names = [t["name"] for t in data["targets"]]
        self.assertIn("_example", names)
        ex = data["targets"][names.index("_example")]
        self.assertTrue(ex["divergence"])
        self.assertTrue(ex["probe_breach"])


class TestDesignCalculators(unittest.TestCase):
    DESIGN = os.path.join(HUB_ROOT, "skills", "lfd-shared", "scripts")

    def test_power_calc_reproduces_worked_example(self):
        out = subprocess.run(
            [sys.executable, os.path.join(self.DESIGN, "power-calc.py"),
             "--bar", "0.80", "--delta", "0.05", "--confidence", "0.95"],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout)["derived_n"], 246)

    def test_leak_audit_verdicts(self):
        def run(bits, cycles, size):
            out = subprocess.run(
                [sys.executable, os.path.join(self.DESIGN, "leak-audit-calc.py"),
                 "--bits-per-call", bits, "--expected-cycles", cycles,
                 "--eval-size", size, "--threshold", "0.25"],
                capture_output=True, text=True, check=True)
            return json.loads(out.stdout)["verdict"]
        self.assertTrue(run("3", "100", "246").startswith("PASS"))
        self.assertTrue(run("50", "500", "100").startswith("FAIL"))

    def test_calculators_require_explicit_valid_policy_inputs(self):
        commands = (
            ["power-calc.py", "--bar", "1", "--delta", "0.05",
             "--confidence", "0.95"],
            ["leak-audit-calc.py", "--bits-per-call", "1",
             "--expected-cycles", "1", "--eval-size", "10"],
            ["ngram-overlap.py", "--solution-dir", ".",
             "--eval-answers-dir", ".", "--n", "0", "--threshold", "0.4"],
            ["compressibility.py", "--solution-dir", ".", "--eval-size", "1",
             "--history-file", os.devnull, "--cycle", "1"],
        )
        for command in commands:
            with self.subTest(command=command[0]):
                result = subprocess.run(
                    [sys.executable, os.path.join(self.DESIGN, command[0]), *command[1:]],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)


class TestDetectorEnforcement(unittest.TestCase):
    def post(self, divergence="false", divergence_mode="advisory",
             probe="", probe_mode="advisory", coverage="",
             coverage_mode="advisory"):
        env = dict(os.environ)
        env["LFD_STATUS_DRYRUN"] = "1"
        return subprocess.run([
            POST_STATUS, "https://github.com/example/target.git", "a" * 40,
            "0.7", "0.6", "0.8", divergence, divergence_mode,
            probe, probe_mode, coverage, coverage_mode,
        ], capture_output=True, text=True, env=env)

    def test_advisory_detector_flags_do_not_fail_status(self):
        result = self.post(divergence="true", probe="below-floor",
                           coverage="below-floor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(": success —", result.stdout)
        self.assertIn("DIVERGENCE", result.stdout)
        self.assertIn("probe: below floor", result.stdout)
        self.assertIn("coverage: below floor", result.stdout)

    def test_each_blocking_detector_can_fail_status(self):
        scenarios = (
            {"divergence": "true", "divergence_mode": "blocking"},
            {"probe": "below-floor", "probe_mode": "blocking"},
            {"coverage": "below-floor", "coverage_mode": "blocking"},
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                result = self.post(**scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(": failure —", result.stdout)

    def test_unknown_detector_policy_fails_closed(self):
        result = self.post(divergence_mode="sometimes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid detector enforcement", result.stderr)


class TestMisc(unittest.TestCase):
    def test_sparkline(self):
        s = lfd_common.sparkline([0.0, 0.5, 1.0, None, 1.0])
        self.assertEqual(len(s), 5)
        self.assertEqual(s[0], "▁")
        self.assertEqual(s[2], "█")
        self.assertEqual(s[3], " ")

    def test_probe_floor_breaches(self):
        row = {"probe": {"operators": {"a": 0.9, "b": 0.5}}}
        self.assertEqual(lfd_common.probe_floor_breaches(row, 0.8), {"b": 0.5})
        self.assertEqual(lfd_common.probe_floor_breaches({}, 0.8), {})

    def test_harness_version_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "a.sh"), "w") as f:
                f.write("hello")
            v1 = lfd_common.harness_version(td)
            v2 = lfd_common.harness_version(td)
            self.assertEqual(v1, v2)
            with open(os.path.join(td, "a.sh"), "w") as f:
                f.write("changed")
            self.assertNotEqual(v1, lfd_common.harness_version(td))


class TestSandbox(unittest.TestCase):
    """Prove the Stage-1 jail: no reading targets/, no network."""

    _docker_probe_result = None
    _sandbox_exec_probe_result = None

    def run_jailed(self, cmd):
        with tempfile.TemporaryDirectory() as checkout, \
             tempfile.TemporaryDirectory() as outdir:
            env = dict(os.environ)
            env.update({
                "LFD_SANDBOX": ("docker" if self._docker_usable()
                                else "sandbox-exec"),
                "SANDBOX_IMAGE": "python:3-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6",
                "SANDBOX_CPUS": "1",
                "SANDBOX_MEMORY": "256m",
                "SANDBOX_PIDS_LIMIT": "64",
            })
            return subprocess.run(
                [os.path.join(HUB_ROOT, "ops", "run-sandboxed.sh"),
                 checkout, outdir, "30", "sh", "-c", cmd],
                capture_output=True, text=True, env=env, timeout=45)

    def _docker_usable(self):
        if self.__class__._docker_probe_result is None:
            try:
                result = subprocess.run(
                    ["docker", "run", "--rm",
                     "python:3-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6",
                     "true"], capture_output=True, timeout=10)
                self.__class__._docker_probe_result = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self.__class__._docker_probe_result = False
        return self.__class__._docker_probe_result

    def _sandbox_exec_usable(self):
        if self.__class__._sandbox_exec_probe_result is None:
            try:
                result = subprocess.run(
                    ["sandbox-exec", "-p", "(version 1) (allow default)", "true"],
                    capture_output=True, timeout=5)
                self.__class__._sandbox_exec_probe_result = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self.__class__._sandbox_exec_probe_result = False
        return self.__class__._sandbox_exec_probe_result

    def _require_backend(self):
        docker_usable = self._docker_usable()
        if os.environ.get("LFD_REQUIRE_DOCKER_TESTS") == "1":
            if not docker_usable:
                self.fail("required Docker sandbox/image is unavailable")
            return
        if not (docker_usable or self._sandbox_exec_usable()):
            self.skipTest("no usable sandbox backend")

    def test_cannot_read_holdout(self):
        self._require_backend()
        probe = os.path.join(HUB_ROOT, "targets", "_example",
                             "eval", "holdout", "case-001.json")
        res = self.run_jailed(f"cat '{probe}'")
        self.assertNotIn("LFD-CANARY-0000000000000001", res.stdout,
                         "sandbox leaked holdout answer content")

    def test_no_network(self):
        self._require_backend()
        res = self.run_jailed(
            "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)\" >/dev/null 2>&1 && echo CONNECTED || echo BLOCKED")
        self.assertNotIn("CONNECTED", res.stdout)
        self.assertTrue(
            "BLOCKED" in res.stdout or res.returncode != 0,
            "sandbox neither blocked the connection nor failed closed")


if __name__ == "__main__":
    unittest.main()
