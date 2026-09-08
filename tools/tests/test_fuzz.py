#!/usr/bin/env python3
"""Fuzz the trust boundary. parse-tag-msg and the row writer are the only
components that face adversarial input (agent-controlled tag messages).
Property under test: for ANY input, the parser never crashes and never
emits a value that isn't a validated float / [lo,hi] / clean model-id /
null. Deterministic (fixed seed) so CI is reproducible.
"""
import json
import os
import random
import string
import subprocess
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
import lfd_common  # noqa: E402

LOG_UTILS = os.path.join(HUB_ROOT, "ops", "log_utils.py")


def random_json_value(rng, depth=0):
    choices = ["int", "float", "str", "bool", "null"]
    if depth < 3:
        choices += ["list", "dict"]
    kind = rng.choice(choices)
    if kind == "int":
        return rng.randint(-10**9, 10**9)
    if kind == "float":
        return rng.choice([rng.uniform(-1e6, 1e6), float("nan"),
                           float("inf"), -0.0, 1e400 if False else 1e308])
    if kind == "str":
        pool = string.printable + "'\";`$(){}[]\\\n\t"
        return "".join(rng.choice(pool) for _ in range(rng.randint(0, 40)))
    if kind == "bool":
        return rng.choice([True, False])
    if kind == "null":
        return None
    if kind == "list":
        return [random_json_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {f"k{i}": random_json_value(rng, depth + 1)
            for i in range(rng.randint(0, 4))}


class TestParseTagMsgFuzz(unittest.TestCase):
    def assert_clean(self, out):
        self.assertIsInstance(out, dict)
        for field in lfd_common.AGENT_NUMERIC_FIELDS:
            v = out[field]
            if v is not None:
                self.assertIsInstance(v, float)
                self.assertFalse(v != v or v in (float("inf"), float("-inf")))
        ci = out["dev_ci"]
        if ci is not None:
            self.assertEqual(len(ci), 2)
            self.assertTrue(all(isinstance(x, float) for x in ci))
        if out["model_id"] is not None:
            self.assertRegex(out["model_id"], r"^[A-Za-z0-9._:/-]{1,128}$")

    def test_never_crashes_never_leaks_unvalidated(self):
        rng = random.Random(1337)
        for _ in range(3000):
            # half well-formed JSON objects, half arbitrary text
            if rng.random() < 0.5:
                raw = json.dumps({rng.choice(
                    list(lfd_common.AGENT_NUMERIC_FIELDS) + ["model_id", "dev_ci", "junk"]):
                    random_json_value(rng) for _ in range(rng.randint(0, 5))})
            else:
                raw = "".join(chr(rng.randint(0, 0x2FFF)) for _ in range(rng.randint(0, 60)))
            # pure function — must be JSON-round-trippable and clean
            out = lfd_common.parse_tag_message(raw)
            json.loads(json.dumps(out))
            self.assert_clean(out)

    def test_cli_contract_matches_pure_function(self):
        for raw in ('{"dev_score": 0.5, "dev_ci": [0.4, 0.6]}', "garbage", "[]"):
            res = subprocess.run([sys.executable, LOG_UTILS, "parse-tag-msg"],
                                 input=raw, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(json.loads(res.stdout),
                             lfd_common.parse_tag_message(raw))


class TestValidateFloatFuzz(unittest.TestCase):
    def test_output_is_always_none_or_finite_float(self):
        rng = random.Random(42)
        for _ in range(2000):
            v = random_json_value(rng)
            out = lfd_common.validate_float(v)
            if out is not None:
                self.assertIsInstance(out, float)
                self.assertFalse(out != out or out in (float("inf"), float("-inf")))

    def test_bounds_respected(self):
        rng = random.Random(7)
        for _ in range(1000):
            v = rng.uniform(-100, 100)
            out = lfd_common.validate_float(v, lo=0.0, hi=1.0)
            if out is not None:
                self.assertGreaterEqual(out, 0.0)
                self.assertLessEqual(out, 1.0)


if __name__ == "__main__":
    unittest.main()
