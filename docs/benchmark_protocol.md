# Benchmark protocol

## Objective

Two empirically separable claims, reported independently.

**Mechanism.** Endpoint correctness conflates information actually transmitted
with information reconstructed by the receiver.

**Method.** Causal supervision from development-only interventions can be turned
into a deployable textual relay policy that competes at the same token budget.

The mechanism claim remains valid even if the policy does not beat every
comparator. The comparative claim is reported only if the frozen paired analysis
supports it.

## Eligibility

The comparison is deliberately narrower than a generic long-context leaderboard,
because the causal quantities require an **inspectable handoff**. A comparator
counts as primary only if it:

1. accepts textual source and the same downstream task description;
2. produces a textual compressed message whose tokens can be audited for
   canonical atom presence;
3. admits an externally enforced token budget;
4. has a peer-reviewed publication and a reproducible implementation or
   checkpoint.

Methods whose compressed state is latent — a KV cache, merged memory units — are
**endpoint-only**. Literal atom presence is undefined for hidden states, and no
substitute is manufactured for them. The exporter separates `PRIMARY_CAUSAL` from
`ENDPOINT_ONLY` at the type level so the two cannot be mixed by accident.

A legacy anchor may be reported for historical continuity without counting toward
the comparative criterion.

## Shared conditions

Every method sees the same relay-visible source, the same frozen downstream task
description, the same receiver, the same tokenizer and the same budget.

**Focal secrecy.** Focal atom identities and values never enter a compressor
prompt or configuration, and this is asserted in code on every call. Without it,
focal sampling would become supervision for query-aware methods, and the
comparison would measure supervision rather than allocation.

**Budget fairness.** No method is compared at its favourite budget against
another at a harder one. Methods exposing ratios or thresholds instead of token
counts have those parameters calibrated **on development data only**, to minimise
`|tokens(M) − B|` subject to `tokens(M) ≤ B`. The adapter is frozen before the
test. No method gets a larger effective context because its native tokenizer
differs.

## Controls

| Control | Role |
|---|---|
| Full context | reference upper bound; **not** budget matched |
| Head truncation | trivial fixed-budget baseline |
| Uniform atoms | uniform selection through the **same renderer** |
| Vanilla relay | fixed-budget relay under the frozen global task |

The uniform-atoms control is mandatory. Holding the renderer fixed, the
policy-versus-uniform difference isolates **allocation**, not presentation. A
learned renderer would turn the comparison into "our allocation plus our
phrasing" versus "their allocation", which is not the claim.

## Reproduction gate

Before any comparator enters the benchmark, all of the following must pass on a
non-test public or native task:

1. environment installs
2. official checkpoint loads
3. canonical native example runs
4. output is textual
5. budget adapter works
6. a selected published result is reproduced within a pre-registered tolerance —
   absolute difference within 2 percentage points, or overlap with the published
   interval where one is given

Debugging happens on public, native or calibration data only. Final-test outputs
are never inspected while adapting an external method. Failure is recorded as
unreproduced; the method is not repaired after looking at the benchmark, and not
replaced by an easier one.

## The registry

`configs/baselines.yaml` records, per method: citation key, official repository,
exact commit, release tag, checkpoint revision, licence, runtime requirements,
install command, the native benchmark selected for reproduction, the expected
public metric, the allowed tolerance and the adapter status.

Fields whose true value is not yet known are **null**, and validation reports
them as unresolved. They are never guessed — a fabricated revision would make the
whole reproducibility chain a fiction.

External source code is not vendored into this repository unless its licence
explicitly permits it and vendoring is necessary. The default is a private clone
with a thin public wrapper.

## CausalRelay

Fitted on **development documents only**.

The training target is the budget-neutral surplus on the predeclared candidate
set. Features are frozen, pre-treatment and source-side: role, source position,
canonical length, local section position, redundancy count, local lexical
context, digit density and slot co-occurrence.

Forbidden as features, enforced in code: final-test receiver outcomes,
availability interventions, `R^-`, `D^+`, `Δ`, matched-skeleton outcomes, and
anything derived from them.

Model family and grid are frozen before the fit. Hyperparameters are selected by
**grouped cross-validation by document** — atom-level folds would place atoms
from the same document on both sides of the split, and since atoms within a
document share one relay realisation and heavy local context, that leaks.

Allocation solves a deterministic 0/1 problem over `max(0, ŝ)` against the
budget, with frozen tie-breaking. No test outcome, intervention or oracle label
touches allocation.

The renderer is deterministic, non-model and shared with the uniform control.

## Metrics

Primary standard metric: `A`.

Causal co-primary diagnostics: `C_comm = A − R̄₀`, and
`C_recon = E[(1−T)·R^-]`.

Secondary: assignment–effect alignment and `T̄`.

Low reconstruction dependence is **not** a win if endpoint accuracy collapses.
`C_recon` is a diagnostic, never the criterion.

## Comparative criterion

A comparative claim is permitted only if, at the matched budget, at least
**three** primary comparators satisfy **both**

```
lower_95CI( A_ours     − A_j     ) > 0
lower_95CI( C_comm_ours − C_comm_j ) > 0
```

by paired document-clustered bootstrap with 10,000 replicates.

The rule lives in code, with a denominator fixed by the registry before the test
runs. Supplying a comparison for a method outside the pre-registered suite is an
error, not a warning.

If the criterion fails, the complete comparison is published without comparative
language. No comparator is deleted, none is substituted, and no metric is
changed after the fact.

Boldface in exported tables is assigned by frozen metric directions once the
analysis has read real outputs. Manual table editing after results are known is
not permitted.

## Multi-hop

Depths 1, 2, 3, 5. The main depth plot shows the policy, the best comparator
selected **on development data only**, and the vanilla relay.

`A^(h)` and `T̄^(h)` are plotted **together**. Reporting `A^(h)` alone would be
precisely the error this project is about.

Depth 1 establishes the mechanism. Depth 3 and beyond is what turns it into a
workflow result, because "endpoint fidelity stays flat while transmission falls"
is only visible once several handoffs have accumulated.
