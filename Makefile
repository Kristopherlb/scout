# Thin aliases over bin/lfd — `make status` beats remembering paths.
.PHONY: status dashboard test lint typecheck coverage poll-all check

status:
	@bin/lfd status

dashboard:
	@bin/lfd dashboard

test:
	@bin/lfd test

poll-all:
	@bin/lfd poll-all

lint:
	@command -v shellcheck >/dev/null 2>&1 || { echo "shellcheck not installed (brew install shellcheck)"; exit 1; }
	shellcheck ops/*.sh bin/lfd templates/target-repo/scripts/target-repo/*.sh
	python3 -m compileall -q tools ops skills/lfd-design/scripts/design
	@command -v ruff >/dev/null 2>&1 && ruff check tools ops || echo "ruff not installed — skipping (CI enforces it)"

typecheck:
	@command -v mypy >/dev/null 2>&1 && mypy || echo "mypy not installed — skipping (CI enforces it)"

coverage:
	@command -v coverage >/dev/null 2>&1 || { echo "coverage not installed (pip install coverage)"; exit 1; }
	coverage run --branch -m unittest discover -s tools/tests
	coverage report
	coverage report --include="*/lfd_common.py" --fail-under=90

# Everything CI checks, locally.
check: lint typecheck test
	python3 tools/ci_checks.py all
