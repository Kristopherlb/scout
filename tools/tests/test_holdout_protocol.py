#!/usr/bin/env python3
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))

import lfd_contract  # noqa: E402
import lfd_holdout_protocol  # noqa: E402

REQUEST = os.path.join(HUB_ROOT, "templates", "target-repo", "scripts",
                       "target-repo", "request-holdout-check.sh")
MATERIALIZE = os.path.join(HUB_ROOT, "templates", "target-repo", "scripts",
                           "target-repo", "materialize-holdout-request.py")
STATUS = os.path.join(HUB_ROOT, "templates", "target-repo", "scripts",
                      "target-repo", "check-holdout-status.sh")


def run(cwd, *args, check=True, env=None):
    return subprocess.run(args, cwd=cwd, check=check, env=env,
                          capture_output=True, text=True)


def git(cwd, *args, check=True):
    return run(cwd, "git", *args, check=check)


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"),
                     "git and bash required")
class TestHoldoutProtocol(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origin = os.path.join(self.tmp, "origin.git")
        self.repo = os.path.join(self.tmp, "target")
        git(self.tmp, "init", "--bare", "-q", self.origin)
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.com")
        with open(os.path.join(self.repo, "solution.py"), "w") as stream:
            stream.write("answer = 42\n")
        os.makedirs(os.path.join(self.repo, ".lfd"))
        with open(os.path.join(self.repo, ".lfd", "holdout-protocol.json"), "w") as stream:
            json.dump({"protocol_version": 1, "tag_prefix": "holdout-check-",
                       "status_context": "lfd/holdout"}, stream)
        git(self.repo, "add", "solution.py", ".lfd/holdout-protocol.json")
        git(self.repo, "commit", "-q", "-m", "initial")
        git(self.repo, "remote", "add", "origin", self.origin)
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.sha = git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def request(self, request_id="0123456789abcdef0123456789abcdef"):
        env = dict(os.environ)
        env["LFD_REQUEST_ID"] = request_id
        return run(self.repo, "bash", REQUEST, "0.5", "0.4", "0.6",
                   check=False, env=env)

    def reject_tag_pushes(self):
        hook = os.path.join(self.origin, "hooks", "pre-receive")
        with open(hook, "w") as stream:
            stream.write("#!/bin/sh\nwhile read old new ref; do\n"
                         "  case \"$ref\" in refs/tags/*) exit 1;; esac\n"
                         "done\nexit 0\n")
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR)
        return hook

    def test_contract_requires_implemented_protocol_version(self):
        contract = lfd_contract.new_contract("demo", self.repo)
        self.assertEqual(contract["holdout"]["protocol_version"], 1)
        contract["holdout"]["protocol_version"] = 2
        with self.assertRaises(lfd_contract.ContractError):
            lfd_contract.validate(contract)

    def test_validator_binds_tag_payload_and_target_sha(self):
        request_id = "0123456789abcdef0123456789abcdef"
        tag = f"holdout-check-v1-{self.sha[:12]}-{request_id}"
        payload = {"schema_version": 1, "request_id": request_id,
                   "requested_sha": self.sha, "dev_score": 0.5,
                   "dev_ci": [0.4, 0.6]}
        parsed = lfd_holdout_protocol.validate_request(
            tag, json.dumps(payload), "holdout-check-", 1, self.sha)
        self.assertEqual(parsed["request_id"], request_id)
        for changed in (
                tag.replace(self.sha[:12], "f" * 12),
                tag.replace(request_id, "f" * 32)):
            with self.assertRaises(lfd_holdout_protocol.ProtocolError):
                lfd_holdout_protocol.validate_request(
                    changed, json.dumps(payload), "holdout-check-", 1, self.sha)
        payload["requested_sha"] = "f" * 40
        with self.assertRaises(lfd_holdout_protocol.ProtocolError):
            lfd_holdout_protocol.validate_request(
                tag, json.dumps(payload), "holdout-check-", 1, self.sha)

    def test_direct_request_pushes_immutable_tag(self):
        result = self.request()
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["status"], "submitted")
        self.assertEqual(document["stage"], "direct")
        tag = document["artifacts"][0]["tag"]
        self.assertEqual(git(self.origin, "rev-parse", f"{tag}^{{commit}}").stdout.strip(),
                         self.sha)
        payload = json.loads(git(self.origin, "tag", "-l", tag,
                                 "--format=%(contents)").stdout)
        self.assertEqual(payload["requested_sha"], self.sha)

    def test_request_rejects_invalid_score_interval(self):
        env = dict(os.environ)
        env["LFD_REQUEST_ID"] = "0123456789abcdef0123456789abcdef"
        result = run(self.repo, "bash", REQUEST, "0.5", "0.6", "0.7",
                     check=False, env=env)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["errors"][0]["code"],
                         "invalid_input")
        self.assertEqual(git(self.origin, "tag", "-l").stdout, "")

    def test_fallback_preserves_caller_and_materializes_transactionally(self):
        hook = self.reject_tag_pushes()
        with open(os.path.join(self.repo, "solution.py"), "a") as stream:
            stream.write("staged = True\n")
        git(self.repo, "add", "solution.py")
        with open(os.path.join(self.repo, "notes.txt"), "w") as stream:
            stream.write("untracked\n")
        before_head = git(self.repo, "rev-parse", "HEAD").stdout
        before_cached = git(self.repo, "diff", "--cached").stdout
        before_status = git(self.repo, "status", "--porcelain").stdout

        result = self.request("fedcba9876543210fedcba9876543210")
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["stage"], "fallback")
        branch = document["artifacts"][0]["branch"]
        request_commit = git(self.origin, "rev-parse", branch).stdout.strip()
        parent = git(self.origin, "rev-parse", f"{request_commit}^").stdout.strip()
        self.assertEqual(parent, self.sha)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout, before_head)
        self.assertEqual(git(self.repo, "diff", "--cached").stdout, before_cached)
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, before_status)
        self.assertNotIn("lfd-request/", git(self.repo, "branch", "--format=%(refname:short)").stdout)

        os.chmod(hook, 0o644)
        clone = os.path.join(self.tmp, "materializer")
        git(self.tmp, "clone", "-q", "--branch", branch, self.origin, clone)
        git(clone, "config", "user.name", "Workflow")
        git(clone, "config", "user.email", "workflow@example.com")
        materialized = run(clone, sys.executable, MATERIALIZE,
                           "--event-sha", request_commit,
                           "--event-ref", f"refs/heads/{branch}", check=False)
        self.assertEqual(materialized.returncode, 0, materialized.stderr)
        mat_doc = json.loads(materialized.stdout)
        self.assertEqual(mat_doc["status"], "success")
        tag = mat_doc["artifacts"][0]["tag"]
        self.assertEqual(git(self.origin, "rev-parse", f"{tag}^{{commit}}").stdout.strip(),
                         self.sha)
        refs = git(self.origin, "for-each-ref", "--format=%(refname)").stdout
        self.assertNotIn(f"refs/heads/{branch}", refs)

    def test_fallback_collision_preserves_preexisting_local_branch(self):
        self.reject_tag_pushes()
        request_id = "fedcba9876543210fedcba9876543210"
        branch = f"lfd-request/{request_id}"
        git(self.repo, "branch", branch, self.sha)
        before = git(self.repo, "rev-parse", branch).stdout.strip()

        result = self.request(request_id)

        self.assertEqual(result.returncode, 4, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["errors"][0]["code"], "fallback_failed")
        self.assertEqual(git(self.repo, "rev-parse", branch).stdout.strip(), before)

    def test_materializer_invalid_request_uses_invalid_input_exit(self):
        result = run(self.repo, sys.executable, MATERIALIZE,
                     "--event-sha", self.sha,
                     "--event-ref", "refs/heads/lfd-request/" + "0" * 32,
                     check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "error")

    def status_with(self, statuses):
        requested = self.request()
        tag = json.loads(requested.stdout)["artifacts"][0]["tag"]
        fake_bin = os.path.join(self.tmp, "fake-bin")
        os.makedirs(fake_bin, exist_ok=True)
        curl = os.path.join(fake_bin, "curl")
        with open(curl, "w") as stream:
            stream.write("#!/bin/sh\nprintf '%s' \"$FAKE_STATUSES\"\n")
        os.chmod(curl, 0o755)
        env = dict(os.environ)
        env.update({"PATH": fake_bin + os.pathsep + env["PATH"],
                    "GITHUB_API_URL": "https://api.example.test",
                    "GH_TOKEN": "test-token", "FAKE_STATUSES": json.dumps(statuses)})
        result = run(self.repo, "bash", STATUS, tag, check=False, env=env)
        return result, json.loads(result.stdout)

    def test_status_ignores_unrelated_aggregate_failure(self):
        result, document = self.status_with([
            {"context": "build", "state": "failure", "description": "broken"},
            {"context": "lfd/holdout", "state": "success", "description": "0.7"},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["status"], "success")
        self.assertEqual(document["artifacts"][0]["description"], "0.7")

    def test_status_returns_pending_when_exact_context_is_absent(self):
        result, document = self.status_with([
            {"context": "build", "state": "success", "description": "ok"},
        ])
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(document["status"], "pending")


if __name__ == "__main__":
    unittest.main()
