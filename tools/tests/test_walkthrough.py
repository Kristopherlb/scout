#!/usr/bin/env python3
import json
import os
import subprocess
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))


class TestPublicWalkthrough(unittest.TestCase):
    def test_walkthrough_exercises_refusal_and_success(self):
        result = subprocess.run(
            [os.path.join(HUB_ROOT, "bin", "lfd"), "walkthrough", "--json"],
            cwd=HUB_ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(set(document), {
            "schema_version", "command", "target", "status", "stage",
            "artifacts", "errors", "next_actions",
        })
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["command"], "walkthrough")
        self.assertEqual(document["status"], "success")
        self.assertEqual(document["stage"], "active")
        stages = [item["stage"] for item in document["artifacts"]]
        self.assertEqual(stages, [
            "contract_valid", "bundle_verified", "dev_scored",
            "calibration_verified", "mechanical_incomplete", "activation_refused",
            "audit_finalized", "activation_succeeded",
        ])
        self.assertEqual(document["artifacts"][2]["score"], 1.0)

    def test_example_bundle_contains_no_private_evidence(self):
        bundle = os.path.join(HUB_ROOT, "targets", "_example", "bundle")
        relative = [os.path.relpath(os.path.join(root, name), bundle)
                    for root, _, names in os.walk(bundle) for name in names]
        forbidden = {"audit-report.json", "audit-mechanical.json",
                     "fixture-judgment.json", "activation.json",
                     "score-holdout.sh", "probe-holdout.sh"}
        self.assertFalse(forbidden.intersection(os.path.basename(path)
                                                for path in relative))

    def test_public_docs_match_runtime(self):
        paths = {
            name: os.path.join(HUB_ROOT, name)
            for name in (
                "README.md", "docs/index.html", "docs/architecture.md",
                "docs/onboarding-a-target.md", "docs/walkthrough.md",
                "SECURITY.md", "CONTRIBUTING.md",
            )
        }
        documents = {}
        for name, path in paths.items():
            with open(path) as stream:
                documents[name] = stream.read()
        self.assertIn("bin/lfd walkthrough", documents["README.md"])
        self.assertIn("bin/lfd walkthrough", documents["docs/index.html"])
        self.assertIn("<prefix>v1-<sha12>-<request-id>",
                      documents["docs/architecture.md"])
        self.assertIn("audit mechanical", documents["docs/onboarding-a-target.md"])
        self.assertIn("activation_refused", documents["docs/walkthrough.md"])
        self.assertIn("advisory | blocking", documents["SECURITY.md"])
        self.assertIn("bin/lfd walkthrough", documents["CONTRIBUTING.md"])
        combined = "\n".join(documents.values())
        for stale in ("Fable", "holdout-check-N", "git commit -am"):
            self.assertNotIn(stale, combined)

    def test_release_workflow_keeps_required_jobs_blocking(self):
        with open(os.path.join(HUB_ROOT, ".github", "workflows", "ci.yml")) as stream:
            workflow = stream.read()
        for job in ("test", "quality", "standards", "sandbox", "gitleaks"):
            self.assertIn(f"\n  {job}:\n", workflow)
        self.assertIn("bin/lfd walkthrough --json", workflow)
        self.assertIn("python3 tools/ci_checks.py public-release", workflow)
        self.assertNotIn("continue-on-error: true", workflow)


if __name__ == "__main__":
    unittest.main()
