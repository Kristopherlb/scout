# Contributing

Thanks for helping improve LFD Evals.

## Before opening a pull request

Use Python 3.9 or newer and install the development-only tools named in
`pyproject.toml`. Run:

```bash
bin/lfd test
python3 tools/ci_checks.py all
python3 tools/ci_checks.py public-release
shellcheck ops/*.sh bin/lfd templates/target-repo/scripts/target-repo/*.sh
ruff check tools ops
mypy
```

Keep changes focused and explain security-boundary changes explicitly. Add or
update tests for behavior changes.

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
