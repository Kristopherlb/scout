# Public-source release posture

## Status

This repository is the sanitized public framework. Real operational hubs stay
separate and private; their Git histories contain evaluation campaigns that
remain recoverable after deletion. Never change a hub's visibility or merge
its history into this repository.

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

## Release checklist

1. Confirm `targets/` contains only `_example` and run the public-release gate.
2. Run the executable walkthrough, unit, policy, lint, type, coverage,
   sandbox-isolation, RAC, and secret checks.
3. Confirm Pages, README, architecture, onboarding, SECURITY, and CONTRIBUTING
   describe the commands and protocol that actually ship.
4. Protect `main` and require every CI and secret-scan job before merge.
5. Create a version tag only after the slice's contract passes on the public
   repository's hosted runners.
