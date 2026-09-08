#!/usr/bin/env python3
"""Stable agent-facing response contract shared by Scout commands."""


SCHEMA_VERSION = 1
EXIT_SUCCESS = 0
EXIT_INVALID = 2
EXIT_PENDING = 3
EXIT_INFRASTRUCTURE = 4


def envelope(command, target=None, status="ok", stage=None, artifacts=None,
             errors=None, next_actions=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "target": target,
        "status": status,
        "stage": stage,
        "artifacts": artifacts or [],
        "errors": errors or [],
        "next_actions": next_actions or [],
    }
