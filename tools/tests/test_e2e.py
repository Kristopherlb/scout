#!/usr/bin/env python3
"""End-to-end pipeline test — exercises the real ops/poll-and-score.sh
against a throwaway local git repo. Hermetic: no network (local file://
remote, post-status in dry-run) and a test-scoped Docker CLI double. Proves
the full path — tag discovery, pinned checkout, liveness gate, scoring,
validated append, dedup, rate limit — actually holds together, which unit
tests of the pieces can't.
"""
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

POLL = os.path.join(HUB_ROOT, "ops", "poll-and-score.sh")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"),
                     "git and bash required")
class TestPipelineE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # --- a throwaway target repo with one commit ---
        self.repo = os.path.join(self.tmp, "target")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        with open(os.path.join(self.repo, "solution.py"), "w") as f:
            f.write("def solve(x):\n    return x * 2\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

        # --- a target-dir the poll will score (hub root stays the real repo) ---
        self.target_dir = os.path.join(self.tmp, "targets", "e2e")
        os.makedirs(os.path.join(self.target_dir, "harness"))
        os.makedirs(os.path.join(self.target_dir, "eval", "holdout"))
        self.log = os.path.join(self.target_dir, "log.jsonl")
        open(self.log, "w").close()

        # Keep the pipeline configured exactly like production while avoiding
        # a daemon, image pull, or network access in this test. The double only
        # implements the `docker info` and `docker run` shapes emitted by
        # ops/run-sandboxed.sh, then executes the liveness command locally.
        self.fake_bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.fake_bin)
        docker = os.path.join(self.fake_bin, "docker")
        with open(docker, "w") as f:
            f.write("""#!/usr/bin/env bash
set -euo pipefail
[ "${1:-}" = info ] && exit 0
[ "${1:-}" = run ] || exit 2
[ "${LFD_TEST_DOCKER_INFRA_FAIL:-0}" = 1 ] && {
  echo "simulated Docker infrastructure failure" >&2
  exit 125
}
shift
checkout=""; output=""; workdir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --rm) shift ;;
    --network=*|--security-opt) shift; [ "${1:-}" = no-new-privileges ] && shift || true ;;
    --cpus=*|--memory=*|--pids-limit=*|--user) shift; [[ "${1:-}" != --* ]] && shift || true ;;
    -v)
      case "$2" in
        *:/work:ro) checkout="${2%:/work:ro}" ;;
        *:/out:rw) output="${2%:/out:rw}" ;;
      esac
      shift 2 ;;
    -w) workdir="$2"; shift 2 ;;
    -e) shift 2 ;;
    *@sha256:*) shift; break ;;
    *) exit 2 ;;
  esac
done
[ "$workdir" = /work ] && cd "$checkout"
export LFD_OUT="$output"
exec "$@"
""")
        os.chmod(docker, 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_config(self, **overrides):
        cfg = {
            "TARGET_NAME": "e2e",
            "TARGET_REPO_URL": self.repo,
            "HOLDOUT_TAG_PREFIX": "holdout-check-",
            "STATUS": "active",
            "MIN_HOURS_BETWEEN_HOLDOUT": "2",
            "DIVERGENCE_WINDOW_CYCLES": "5",
            "BUDGET_MAX_HOLDOUT_RUNS": "100",
            "PROBE_ON_HOLDOUT": "off",
            "PROBE_EVERY_K": "3",
            "PROBE_FLOOR": "0.8",
            "BUILD_CMD": "", "BOOT_CMD": "", "HEALTH_CHECK": "",
            "LIVENESS_EXEMPT": "test fixture",
            "LIVENESS_TIMEOUT": "30",
            "LFD_SANDBOX": "docker",
            "SANDBOX_IMAGE": "python:3-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6",
            "SANDBOX_CPUS": "1",
            "SANDBOX_MEMORY": "256m",
            "SANDBOX_PIDS_LIMIT": "64",
        }
        cfg.update(overrides)
        with open(os.path.join(self.target_dir, "config.env"), "w") as f:
            f.write("".join(f'{k}="{v}"\n' for k, v in cfg.items()
                            if v is not None))

    def write_scorer(self, body):
        path = os.path.join(self.target_dir, "harness", "score-holdout.sh")
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o755)
        with open(os.path.join(self.target_dir, "audit-report.json"), "w") as f:
            json.dump({
                "verdict": "PASS",
                "harness_version": lfd_common.harness_version(
                    os.path.join(self.target_dir, "harness")),
            }, f)
        with open(os.path.join(self.target_dir, "calibration-report.json"), "w") as f:
            json.dump({
                "good_score": 0.9,
                "good_ci": [0.85, 0.95],
                "bad_score": 0.2,
                "bad_ci": [0.1, 0.3],
            }, f)

    def push_tag(self, n, dev_score=0.5):
        msg = json.dumps({"dev_score": dev_score, "dev_ci": [dev_score - 0.05,
                                                             dev_score + 0.05]})
        git(self.repo, "tag", "-a", f"holdout-check-{n}", "-m", msg)

    def run_poll(self, summary=None, extra_env=None):
        env = dict(os.environ)
        env["PATH"] = self.fake_bin + os.pathsep + env["PATH"]
        env["LFD_STATUS_DRYRUN"] = "1"
        env.pop("EVAL_REPO_STATUS_TOKEN", None)
        if extra_env:
            env.update(extra_env)
        if summary:
            env["GITHUB_STEP_SUMMARY"] = summary
        return subprocess.run(["bash", POLL, self.target_dir],
                              capture_output=True, text=True, env=env)

    # ------------------------------------------------------------------

    def test_happy_path_scores_and_appends_one_row(self):
        self.write_config()
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score": 0.70, "ci_low": 0.65, "ci_high": 0.75}\'\n')
        self.push_tag(1)
        summary = os.path.join(self.tmp, "summary.md")
        res = self.run_poll(summary=summary)
        self.assertEqual(res.returncode, 0, res.stderr)

        rows = lfd_common.read_log(self.log)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["tag"], "holdout-check-1")
        self.assertEqual(row["holdout_score"], 0.70)
        self.assertEqual(row["liveness"], "ok")
        self.assertEqual(row["dev_score"], 0.5)           # from validated tag msg
        self.assertIn("harness_version", row)
        # provenance: sha is the real tagged commit
        expected_sha = subprocess.run(
            ["git", "-C", self.repo, "rev-list", "-n", "1", "holdout-check-1"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(row["sha"], expected_sha)
        # job summary rendered
        with open(summary) as f:
            self.assertIn("| e2e |", f.read())

    def test_dedup_second_poll_adds_no_row(self):
        self.write_config()
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score": 0.7, "ci_low": 0.6, "ci_high": 0.8}\'\n')
        self.push_tag(1)
        self.run_poll()
        self.run_poll()   # same tag already scored
        self.assertEqual(len(lfd_common.read_log(self.log)), 1)

    def test_rate_limit_skips_second_tag_same_run(self):
        self.write_config(MIN_HOURS_BETWEEN_HOLDOUT="2")
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score": 0.7, "ci_low": 0.6, "ci_high": 0.8}\'\n')
        self.push_tag(1)
        self.push_tag(2)
        self.run_poll()
        rows = lfd_common.read_log(self.log)
        # first scored; second inside the 2h window → deferred
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tag"], "holdout-check-1")

    def test_liveness_failure_scores_zero(self):
        self.write_config(HEALTH_CHECK="exit 1")
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score": 0.99, "ci_low": 0.98, "ci_high": 1.0}\'\n')
        self.push_tag(1)
        res = self.run_poll()
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = lfd_common.read_log(self.log)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["liveness"], "liveness_failed")
        self.assertEqual(rows[0]["holdout_score"], 0)   # scorer's 0.99 never trusted

    def test_sandbox_infrastructure_failure_aborts_without_score(self):
        self.write_config(HEALTH_CHECK="true")
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score":1,"ci_low":1,"ci_high":1}\'\n')
        self.push_tag(1)
        res = self.run_poll(extra_env={"LFD_TEST_DOCKER_INFRA_FAIL": "1"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("sandbox infrastructure failed", res.stderr)
        self.assertIn("simulated Docker infrastructure failure", res.stderr)
        self.assertEqual(len(lfd_common.read_log(self.log)), 0)

    def test_inactive_target_not_polled(self):
        self.write_config(STATUS="paused")
        self.write_scorer('#!/usr/bin/env bash\necho \'{"score":1,"ci_low":1,"ci_high":1}\'\n')
        self.push_tag(1)
        self.run_poll()
        self.assertEqual(len(lfd_common.read_log(self.log)), 0)

    def test_missing_operational_config_fails_closed(self):
        self.write_config(BUDGET_MAX_HOLDOUT_RUNS=None)
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score":1,"ci_low":1,"ci_high":1}\'\n')
        self.push_tag(1)
        res = self.run_poll()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("BUDGET_MAX_HOLDOUT_RUNS", res.stderr)
        self.assertEqual(len(lfd_common.read_log(self.log)), 0)

    def test_active_target_requires_docker_backend(self):
        self.write_config(LFD_SANDBOX="none")
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score":1,"ci_low":1,"ci_high":1}\'\n')
        self.push_tag(1)
        res = self.run_poll()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("active targets require LFD_SANDBOX=docker", res.stderr)
        self.assertEqual(len(lfd_common.read_log(self.log)), 0)

    def test_mutable_sandbox_image_is_rejected(self):
        self.write_config(SANDBOX_IMAGE="python:3-slim")
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score":1,"ci_low":1,"ci_high":1}\'\n')
        self.push_tag(1)
        res = self.run_poll()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("SANDBOX_IMAGE must be pinned", res.stderr)
        self.assertEqual(len(lfd_common.read_log(self.log)), 0)

    def test_malicious_tag_message_neutralized_end_to_end(self):
        self.write_config()
        self.write_scorer('#!/usr/bin/env bash\n'
                          'echo \'{"score": 0.5, "ci_low": 0.4, "ci_high": 0.6}\'\n')
        # hostile dev_score in the tag the "agent" controls
        msg = json.dumps({"dev_score": "__import__('os').system('touch /tmp/lfd_pwn')",
                          "dev_ci": [0, 1], "model_id": "x; rm -rf ~"})
        git(self.repo, "tag", "-a", "holdout-check-1", "-m", msg)
        self.run_poll()
        row = lfd_common.read_log(self.log)[0]
        self.assertIsNone(row["dev_score"])     # rejected, stored as null
        self.assertIsNone(row["model_id"])
        self.assertFalse(os.path.exists("/tmp/lfd_pwn"))


if __name__ == "__main__":
    unittest.main()
