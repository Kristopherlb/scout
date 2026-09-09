#!/usr/bin/env python3
"""Idempotent managed instruction blocks for supported agent runtimes."""
import os

BEGIN = "<!-- BEGIN SCOUT LFD MANAGED BLOCK -->"
END = "<!-- END SCOUT LFD MANAGED BLOCK -->"
BODY = """## Scout LFD execution

When `.lfd/bundle-manifest.json` is present and the task concerns the Scout
optimization loop, read `.agents/skills/lfd-execute/SKILL.md` before acting.
Use the bundled scoring, request, and status commands exactly as documented.
Do not create custom Git request plumbing, scrape aggregate CI status, or try
to locate private holdout, design, audit, or operator evidence.
"""
BLOCK = f"{BEGIN}\n{BODY.rstrip()}\n{END}"
DESTINATIONS = (
    "AGENTS.md",
    "CLAUDE.md",
    os.path.join(".cursor", "rules", "scout-lfd.mdc"),
    os.path.join(".github", "copilot-instructions.md"),
)


class ShimError(ValueError):
    def __init__(self, code, path, message):
        self.code = code
        self.path = path
        super().__init__(f"{code} at {path}: {message}")


def _path_has_symlink(checkout, relative):
    current = checkout
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            return True
    return False


def _existing(path):
    if not os.path.exists(path):
        return ""
    if not os.path.isfile(path):
        raise ShimError("shim_conflict", path, "destination is not a regular file")
    with open(path) as stream:
        return stream.read()


def _bounds(path, content):
    begins = content.count(BEGIN)
    ends = content.count(END)
    if begins != ends or begins > 1:
        raise ShimError("malformed_managed_block", path,
                        "managed markers must appear together exactly once")
    if begins == 0:
        return None
    start = content.index(BEGIN)
    finish = content.index(END, start) + len(END)
    return start, finish


def preflight_all(checkout):
    checkout = os.path.abspath(checkout)
    for relative in DESTINATIONS:
        path = os.path.join(checkout, relative)
        if _path_has_symlink(checkout, relative):
            raise ShimError("shim_conflict", relative,
                            "managed instruction path contains a symbolic link")
        _bounds(path, _existing(path))


def apply_all(checkout):
    checkout = os.path.abspath(checkout)
    preflight_all(checkout)
    for relative in DESTINATIONS:
        path = os.path.join(checkout, relative)
        if _path_has_symlink(checkout, relative):
            raise ShimError("shim_conflict", relative,
                            "managed instruction path contains a symbolic link")
        content = _existing(path)
        bounds = _bounds(path, content)
        if bounds:
            updated = content[:bounds[0]] + BLOCK + content[bounds[1]:]
        else:
            prefix = content.rstrip()
            updated = (prefix + "\n\n" if prefix else "") + BLOCK + "\n"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as stream:
            stream.write(updated)


def verify_all(checkout):
    checkout = os.path.abspath(checkout)
    for relative in DESTINATIONS:
        path = os.path.join(checkout, relative)
        if _path_has_symlink(checkout, relative):
            raise ShimError("shim_conflict", relative,
                            "managed instruction path contains a symbolic link")
        content = _existing(path)
        bounds = _bounds(path, content)
        if bounds is None or content[bounds[0]:bounds[1]] != BLOCK:
            raise ShimError("shim_drift", relative, "managed Scout block is missing or changed")
    return {"status": "ok", "files": len(DESTINATIONS)}
