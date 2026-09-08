## Summary

Describe the problem and the behavior this change introduces.

## Verification

- [ ] `bin/lfd test`
- [ ] `python3 tools/ci_checks.py all`
- [ ] `python3 tools/ci_checks.py public-release`
- [ ] Lint and type checks pass

## Security boundary

- [ ] This change contains no real target data, holdouts, canaries, private
      repository identifiers, credentials, or generated evaluation artifacts.
- [ ] Runtime configuration, isolation, and egress changes are explained above.
