# LFD Evals

LFD Evals is an open-source toolkit for designing and operating blinded,
anti-Goodhart evaluations for autonomous coding agents. It keeps fast
developer feedback in the target repository while scoring hidden cases in a
separate, trusted environment.

> [!IMPORTANT]
> This public source repository contains only the framework and a synthetic
> `_example` fixture. Real holdouts, canaries, target configuration, and score
> histories belong in a separate **private operational repository**. Never add
> real evaluation material to the public repository, even temporarily.

## How it works

```text
PUBLIC SOURCE                    PRIVATE OPERATIONAL HUB             TARGET REPO
framework + synthetic fixture → real holdouts + scoring runtime ← requests by tag
                                 results by commit status          agent works here
```

The target asks for a holdout check with an annotated
`holdout-check-N` tag. The private hub checks out the pinned commit, runs
untrusted target code without network access or holdout visibility, compares
outputs outside the sandbox, and returns only a bounded status result.

The framework includes:

- a target registry and onboarding CLI;
- two-stage, sandboxed scoring orchestration;
- liveness, calibration, and audit activation gates;
- canary, mutation, divergence, and coverage-variance checks;
- terminal status, review, retrospective, and HTML dashboard tools;
- a reusable LFD design skill under `skills/lfd-design/`;
- a synthetic fixture that exercises healthy and adversarial signals.

## Quick start

Requirements: Python 3.9 or newer, Git, Bash, and `jq`. Docker is strongly
recommended for scoring untrusted target code. Development checks also use
ShellCheck, Ruff, Mypy, and Coverage.

```bash
bin/lfd status
bin/lfd dashboard
bin/lfd test
python3 tools/ci_checks.py all
python3 tools/ci_checks.py public-release
```

`bin/lfd status` and `bin/lfd dashboard` work immediately against the
synthetic `targets/_example` data.

## Create a private operational hub

Do not put real eval data in a public GitHub fork. Create a separate private
repository from a source release instead:

1. Copy a tagged source release into a new directory without its `.git`
   directory.
2. Initialize a new Git repository and create a private remote.
3. Restrict read access to trusted humans. Evaluated agents and their
   credentials must never be able to read it.
4. Run `bin/lfd new-target <name> <repo-url>` and follow
   [the onboarding guide](docs/onboarding-a-target.md).
5. Configure the target access token and polling schedule in the private
   repository only.

Keep the public project as a read-only upstream for framework updates. Review
every upstream change before applying it to the private hub, and never send
private hub commits back upstream.

## Repository layout

| Path | Purpose |
|---|---|
| `bin/lfd` | Command-line entry point |
| `tools/` | Registry, audit, status, dashboard, and policy tools |
| `ops/` | Trusted polling, sandboxing, scoring, and status runtime |
| `templates/target-repo/` | Files copied into a repository under evaluation |
| `skills/lfd-design/` | Agent-neutral LFD design skill source |
| `targets/_example/` | Synthetic demonstration data only |
| `docs/` | Architecture, onboarding, and release guidance |

Agent tools discover skills in different locations. Copy or link
`skills/lfd-design/` into the skill directory used by your agent runtime; keep
this directory as the canonical source.

## Security boundary

The open-source framework is public; an operational hub with real evaluation
material is private. That separation is part of the design, not an optional
deployment preference. Read [SECURITY.md](SECURITY.md) and
[the architecture guide](docs/architecture.md) before onboarding a target.

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md).
Public pull requests must pass the `public-release` gate and therefore cannot
contain real target directories or generated evaluation artifacts.

## License

Licensed under the [Apache License 2.0](LICENSE).
