# Goal: compute integer squares

## Stage 0 — Build to spec

Implement a program that reads an integer input and returns its square. Keep
the ordinary checks green before using the development scorer.

## Target

Exact-match accuracy in both directions: wrong, missing, or extra answers score
zero. Bar: 1.0 on the blinded holdout. This toy scorer reports the observed
case range rather than making an inferential interval claim. Holdout size: 2 cases; this intentionally tiny synthetic
fixture demonstrates mechanics and makes no population-level performance claim.

## Constraints

- `capacity_caps` limits solution source to a compact implementation.
- `diff_scope` rejects a checkpoint that changes unrelated files.
- `canary_scan` rejects evidence copied from private answers.
- `ngram_overlap` rejects suspicious phrase overlap with private material.
- `compressibility` bounds lookup-table-shaped source growth.

## Cycle protocol

Run the visible scorer, preregister one change in `LOG.md`, stage only intended
paths, and commit that coherent change. Request a holdout only through the
bundled versioned request command; read only its bounded status.

## Entropy and escalation

After an unconfirmed movement, change approach rather than tuning the same
knob. Halt for hub-side patching on divergence, detector failure, or bundle
drift. The executor never patches this loss function.

## Stop conditions

Stop when the holdout lower interval reaches 1.0 or a configured budget is
exhausted. This fixture is synthetic and is not an operational campaign.
