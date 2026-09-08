# Open-source readiness audit

## Status

The repository-local release candidate is ready for a clean-history public
repository. Do **not** change the visibility of the private source repository:
its Git history contains real evaluation campaigns that remain recoverable
after deletion.

## Sanitization performed

- Removed both real evaluation campaigns (1,179 files): holdouts, canaries,
  generated cases, target bundles, harnesses, configuration, logs, reports, and
  design notes.
- Removed tracked Coverage and compressibility-history artifacts and added
  ignore rules for future local output.
- Retained only the synthetic, underscore-prefixed `_example` fixture.
- Replaced provider- and account-specific onboarding examples with neutral
  configuration.
- Moved the LFD skill to the canonical, agent-neutral `skills/` directory.
- Replaced the private-repository access-review workflow with a public-source
  data-boundary gate.

## Security and runtime audit

- Full source history was scanned for recognized secrets before sanitization;
  no findings were reported. This does not make the old history publishable,
  because holdout content is sensitive even when it is not a credential.
- Public CI rejects any non-fixture `targets/<name>/` directory.
- The public polling workflow is manual-only; an operator must choose a
  schedule in the private deployment.
- Sandbox backend, digest-pinned image, resource limits, budgets, cadence, and
  probe policy come from target configuration rather than runtime fallbacks.
- Missing operational configuration fails closed.
- Active polling requires Docker and fails closed if it is unavailable;
  non-container backends remain available only for direct tests or development.
- CI has a blocking Docker job that pulls the configured digest and verifies
  both network denial and holdout-file isolation.
- Sandbox infrastructure failures abort scoring without writing a target score.
- Polling re-runs activation gates at runtime; a CI bypass cannot activate an
  unaudited, uncalibrated, or non-live scorer.
- A configured probe failure stops the scoring run instead of degrading to a
  false no-probe success.
- GitHub API endpoints and status credentials are supplied by the execution
  environment rather than embedded in runtime code.
- Third-party GitHub Actions and CI container images are pinned to immutable
  revisions.

## Community and legal files

- Apache License 2.0
- `NOTICE`
- contribution guide
- code of conduct
- security policy and private-reporting instructions
- structured bug and feature issue forms
- pull-request checklist

Before publishing, confirm that the repository owner has the right to license
all retained source and documentation under Apache-2.0. The sanitized snapshot
contains no declared runtime dependencies.

## Publication checklist

1. Build the release repository from a clean snapshot of this candidate; do
   not copy `.git` or connect the private source as a public remote.
2. Create a new, empty public repository and push the clean snapshot as its
   first commit.
3. Enable private vulnerability reporting.
4. Protect `main` and require the CI and secret-scan jobs before merge.
5. Configure repository description, topics, issue labels, and Discussions if
   desired.
6. Re-run unit, policy, lint, type, coverage, sandbox, and secret checks from
   the public clone.
7. Tag the first release only after those checks pass on GitHub-hosted runners.
