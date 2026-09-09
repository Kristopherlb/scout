#!/usr/bin/env python3
"""Tiny executable target used only by Scout's public walkthrough."""
import json
import os
import sys


def solve(item):
    return item["value"] * item["value"]


if "--batch" in sys.argv:
    output = os.environ["LFD_OUT"]
    with open(os.path.join(output, "inputs.json")) as stream:
        cases = json.load(stream)
    with open(os.path.join(output, "predictions.json"), "w") as stream:
        json.dump([{"id": case["id"], "answer": solve(case["input"])}
                   for case in cases], stream)
else:
    print(json.dumps({"answer": solve(json.load(sys.stdin))}))
