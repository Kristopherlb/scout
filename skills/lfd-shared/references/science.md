# Scientific basis for Scout LFD

This directory is a non-invocable knowledge base shared by the narrow Scout
skills. No `SKILL.md` belongs here.

## Measurement model

The visible development score is a high-frequency proxy; the blinded holdout
score estimates performance on the task distribution. Optimizing a proxy hard
enough exposes gaps between it and the desired behavior (Goodhart's law), so
Scout combines blinding, bounded feedback, multiple detectors, and periodic
independent judgment rather than treating any one metric as truth.

## Methods

- **Power analysis** selects enough cases to distinguish the acceptance bar
  from the smallest meaningful change at the chosen confidence.
- **Bootstrap confidence intervals** resample case-level outcomes, expressing
  uncertainty in a score rather than pretending the sample is the population.
- **Goodhart taxonomy** classifies shortcuts as regressional, extremal, causal,
  or adversarial so the design uses the corresponding fence family.
- **Contamination checks** combine exact per-run canaries with fuzzy n-gram
  overlap. Exact proof and heuristic suspicion remain distinct.
- **Mutation probes** transform inputs by named operators and retain
  per-operator scores, revealing which generalization axis is brittle.
- **Controlled ablation and preregistration** change one coherent variable per
  cycle and record the expected movement before the result is known.
- **Divergence, coverage variance, and compressibility** form a detector
  battery for proxy over-optimization and lookup-table behavior. Their
  configured `advisory|blocking` policy is separate from their mathematics.

The private/public topology is part of the experiment: target code generates
outputs without answers or network access, and trusted hub code compares those
outputs afterward. A bounded aggregate status is deliberately less informative
than per-case failures because feedback capacity itself can leak the holdout.
