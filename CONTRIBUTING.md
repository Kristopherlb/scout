# Contributing

Thanks for helping improve Scout.

## Before opening a pull request

Use Python 3.9 or newer and install the development-only tools named in
`pyproject.toml`. Run:

```bash
bin/lfd walkthrough
bin/lfd test
python3 tools/ci_checks.py all
python3 tools/ci_checks.py public-release
shellcheck bin/lfd
find ops templates skills targets/_example -type f -name '*.sh' -print0 | xargs -0 shellcheck
ruff check tools ops skills/lfd-shared/scripts
mypy
```

Keep changes focused and explain security-boundary changes explicitly. Add or
update tests for behavior changes. Work lands in independently revertible
slices; `main` must remain truthful, sterile, documented, and green after each
merge. Skills wrap stable CLI commands rather than reimplementing runtime logic.

## Standards and architecture changes

Scout keeps its requirements and accepted architecture decisions in `rac/` and
maps every normative requirement to a control in `standards/controls.json`.
The RAC standards tool requires Python 3.11 or newer; its exact version is
recorded in `standards/rac-version.txt`, and all transitive dependencies are
hash-locked in `standards/rac-requirements.lock`. Install the lock, then run:

```bash
python3 -m pip install --require-hashes -r standards/rac-requirements.lock
python3 tools/check_standards.py all
rac gate rac/
rac export rac/ --agent-rules --check
```

If an accepted decision changes, regenerate the managed agent guidance with
`rac export rac/ --agent-rules` and commit the result. New blocking source
guardrails should include a negative regression test proving that the forbidden
state is rejected. Human-review controls must identify their review procedure
instead of claiming executable coverage.

## Never submit evaluation secrets

Public contributions may include underscore-prefixed synthetic fixtures such
as `targets/_example`. They must not include real target directories, holdout
answers, canaries, run logs, private repository names, credentials, or generated
analysis artifacts. If any such material is committed, stop and report it
privately as described in [SECURITY.md](SECURITY.md); deleting it in a later
commit does not remove it from history.

## Contributions and licensing

Unless you explicitly state otherwise, contributions intentionally submitted
for inclusion are licensed under Apache-2.0, as described in Section 5 of the
[LICENSE](LICENSE). Do not submit code or data you do not have the right to
license.

## Conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
