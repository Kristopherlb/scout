## Summary

Describe the problem and the behavior this change introduces.

## Verification

- [ ] `bin/lfd test`
- [ ] `python3 tools/ci_checks.py all`
- [ ] `python3 tools/ci_checks.py public-release`
- [ ] `python3 tools/check_standards.py all`
- [ ] `rac gate rac/`
- [ ] `rac export rac/ --agent-rules --check`
- [ ] Lint and type checks pass

## Standards impact

- [ ] Applicable requirements and decisions under `rac/` are linked or updated.
- [ ] Every new normative requirement has one entry in `standards/controls.json`.
- [ ] Every new blocking source guardrail has a negative regression test, or the
      reason for relying on human review is explained above.
- [ ] Changes to `bin/lfd` only route and delegate; application behavior remains
      in command modules.

## Security boundary

- [ ] This change contains no real target data, holdouts, canaries, private
      repository identifiers, credentials, or generated evaluation artifacts.
- [ ] Runtime configuration, isolation, and egress changes are explained above.
- [ ] I reviewed the complete touched runtime path for embedded operational
      choices, hidden defaults, bypasses, fake success, and documentation drift.
- [ ] Every scoring-log write still routes through `ops/log_utils.py`; this
      change adds no alternate Python or shell writer.
