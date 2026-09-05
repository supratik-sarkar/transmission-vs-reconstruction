# Architecture

## Two workspaces

**Public repository** — code, tests, documentation, configuration schemas and
frozen protocol specifications. No credential, no raw source, no run output.

**Private runtime workspace** — credentials, raw sources, snapshots, calibration
material, external clones, model caches, run outputs, logs and freeze material
containing local provenance.

The private workspace is deliberately **not** a Git repository, and must sit
outside the public checkout. Its location is supplied at runtime through
`HANDOFF_PRIVATE_HOME`; no path belonging to any particular machine appears in
this repository.

## Dependency posture

The scientific core — corpus framing, atomization, sampling, matching, editing,
estimators, bootstrap, provenance, export scaffolding — depends only on the
standard library and NumPy.

That is a deliberate choice rather than minimalism for its own sake: the design
invariants must be checkable without installing the optional extras, and a core
that needs a heavyweight stack is a core whose correctness is harder to
establish.

The claim is about **dependencies only**. The supported runtime is Python 3.12
and nothing here targets an older interpreter: the source uses PEP 695 generics,
`enum.StrEnum` and `datetime.UTC` natively, and `scripts/run_tests_stdlib.py`
refuses to start below 3.12.

Everything else is an optional extra with a clear failure mode:

| Extra | Enables | Without it |
|---|---|---|
| `tokenizer` | the frozen tokenizer | a test-only fallback, which refuses to be used for a real run unless explicitly permitted |
| `ml` | the gradient-boosted policy | an exact dependency-free ridge ablation |
| `figures` | figure export | table export still works |
| `data` | HTML source conversion | plain-text sources still work |
| `providers` / `hf` | model calls | the deterministic mock |

Torch is never required by the coordinating code, and CUDA dependencies are never
installed on macOS.

## Module map

```
corpus/        section extraction, normalisation, source frame + hash, retrieval interface
atomizer/      rule-based Tier-1 extraction, taxonomy, verification, eligibility, IO
sampling/      role-stratified design, inclusion probabilities, eligibility
matcher/       canonicalisation, token-boundary matching, blinded validation
editing/       availability editor, sham edits, non-focal invariance
relay/         the frozen global downstream task and the focal-leak guard
receiver/      slot schemas, the single shared receiver prompt, chance baselines
interventions/ matched skeleton, prior probe, budget-neutral swaps
causal/        estimands, weighting, sham regions, targeting, gates, multi-hop
causalrelay/   features, model, renderer, allocation
baselines/     adapter API, controls, registry, external adapters
benchmark/     orchestration, reproduction gate, comparative rule
inference/     document-clustered bootstrap, paired comparisons
provenance/    hashing, manifests, freeze records, results manifest
export/        table fragments, figures, manuscript guard
stages/        stage specifications and execution guards
compute/       device routing and diagnostics
privacy/       repository scan and public/private boundary
```

## Invariants enforced in code

These are checked mechanically because each protects a scientific claim, and
each is the kind of thing that a careful person nevertheless gets wrong once.

| Invariant | Where |
|---|---|
| atom inventory lies inside the relay-visible frame | `corpus.frame.assert_inventory_within_frame` |
| `Σ π = k` and `π > 0` everywhere | `sampling.design`, `selftest` |
| the decomposition closes with zero residual | `causal.estimands`, `selftest` |
| selection bias equals its closed form | `causal.estimands`, `selftest` |
| sham correction is mechanism-dependent in sign | `causal.sham_partial`, `selftest` |
| non-focal content is invariant under an edit | `editing.invariance` |
| deletion removes **every** canonical-equivalent occurrence | `editing.editor` |
| renderer and matcher agree on inserted content | `editing.editor` |
| matched-skeleton arms share slot structure and focal absence | `interventions.skeleton` |
| focal values never reach a compressor | `relay.task.assert_no_focal_leak` |
| every adapter respects the hard budget | `baselines.base` |
| endpoint-only methods cannot populate causal metrics | `benchmark.runner` |
| the policy never sees test labels | `causalrelay.model`, `causalrelay.allocate` |
| cross-validation folds are grouped by document | `causalrelay.model.grouped_folds` |
| allocation is order-independent | `causal.targeting.knapsack`, `selftest` |
| paired bootstrap requires a common document set | `inference.bootstrap` |
| freeze records reject placeholder values | `provenance.freeze` |
| the private workspace is non-Git and outside the repository | `privacy.boundary` |

## Execution posture

Nothing in this repository executes an experiment. Stages are **declared** with
their guard conditions; the guards fail closed and are ordered so that model
pinning is checked before anything can reach a provider.

Retrieval, live provider calls and external comparator entry points are explicit
integration points that raise rather than silently degrade. A method that is not
installed and reproduced reports `NOT_READY`; it is never approximated.
