# Transmission vs Reconstruction

A causal measurement and benchmarking toolkit for distinguishing **transmitted**
from **reconstructed** information in chained language-model workflows.

When one model hands work to another, the receiving model routinely states
information the sending model never communicated: a pretrained receiver
reconstructs plausible content from surrounding context and from what it already
knows. Endpoint correctness cannot separate the two, because an item that
survived a handoff and an item that was dropped and then guessed produce
identical downstream text.

---

## Why this matters

A relay sends only

> North America margins improved.

and the receiver writes

> North America margins improved by 6.2% in FY2023.

The final sentence may be entirely correct. It does not follow that any of it was
communicated: the figure and the period may have been supplied by the receiver
from surrounding cues and prior knowledge.

The two mechanisms fail differently. Transmitted information does not require the
receiver to reconstruct anything. Reconstructed information evaporates when the
entity is unfamiliar or the domain shifts. A pipeline measured only at the
endpoint can therefore report high fidelity on familiar cases and degrade sharply
in deployment, with no diagnostic signal in between.

The obstacle is causal rather than statistical. One might try to estimate
reconstructability from the items a relay happened to omit — but the relay
*chooses* what to omit, plausibly dropping what it judges predictable, so the
omitted set is selected on the very quantity being measured.

---

## Core idea

Each factual item in a source document is treated as an **atom** carrying
potential outcomes under two availabilities: present in the handoff, or absent
from it. The relay is modelled as a **non-ignorable assignment mechanism** — the
sender, not the experimenter, decides which atoms are transmitted.

The pieces the toolkit measures:

| Quantity | Reads as |
|---|---|
| `R^-` | recovery when the focal atom is **absent** but everything else the relay actually sent remains |
| `D^+` | recovery when the focal atom is **present** |
| `Δ^avail = D^+ − R^-` | the availability transmission surplus |
| `T̄` | the rate at which atoms survive the handoff |
| `R̄₀` | population reconstruction baseline |
| `C_comm = A − R̄₀` | net causal communication contribution (signed) |
| `C_recon = E[(1−T)·R^-]` | correctness that depended on reconstruction |
| `Cov(T, Δ)` | assignment–effect alignment |

Endpoint fidelity then decomposes without residual:

```
A  =  R̄₀  +  T̄·Δ̄  +  Cov(T, Δ)
   reconstruction   volume     alignment
```

The identity is elementary — it is the law of total expectation for a binary
treatment — and the toolkit claims no algebraic novelty for it. What matters is
that each term is separately **identifiable by intervention** rather than by
assumption, and that they answer different questions.

Two consequences drive the whole design:

- **Endpoints do not identify the triple.** A two-parameter family of causal
  worlds induces exactly the same observed law while realising different values
  of all three terms.
- **The observational estimator is biased by `−Cov(T, R^-)/(1−T̄)`.** A relay that
  preferentially drops recoverable content is precisely the relay whose
  observational estimate misleads most — so the better the compressor, the worse
  the naive estimate.

A note on wording: `Cov(T, Δ)` is called **assignment–effect alignment**, not
"communicative competence". A positive value says transmitted atoms tend to carry
larger surplus. That is an association, not evidence of deliberate or efficient
allocation.

---

## What the toolkit does

- **Corpus preparation** — deterministic section extraction, normalisation and
  construction of a hashed *relay-visible source frame*.
- **Atom extraction** — rule-based, no model judge, with human-verification
  tooling and pre-treatment eligibility filtering.
- **Focal sampling** — fixed-size role-stratified sampling *before* the relay
  runs, with recorded inclusion probabilities.
- **Handoff measurement** — token-boundary canonical matching for entities,
  scopes, periods, numerics and references.
- **Causal interventions** — availability edits with mechanical non-focal
  invariance checks, semantics-preserving sham edits, matched-skeleton
  construction, and budget-neutral swaps.
- **Estimation** — design-weighted Horvitz–Thompson and Hájek estimators, a
  two-phase form, sham partial identification, and document-clustered bootstrap.
- **Comparator adapters** — a common `compress()` interface with hard budget
  enforcement and focal secrecy.
- **`CausalRelay`** — a deployable relay policy fitted on development data only.
- **Provenance** — artifact manifests, freeze records and a results manifest that
  binds every exported table and figure to the run that produced it.
- **Export** — code-generated LaTeX fragments and figures; no number is typed in
  by hand.

---

## Installation

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras, installed only when needed:

```bash
pip install -e ".[ml]"          # scikit-learn, for the gradient-boosted policy
pip install -e ".[figures]"     # matplotlib, for figure export
pip install -e ".[tokenizer]"   # tiktoken, for the frozen tokenizer
pip install -e ".[providers]"   # model provider clients
```

The scientific core — sampling, matching, editing, estimators, bootstrap,
provenance — depends only on the standard library and NumPy, so the invariants
can be checked without installing the optional extras. This is a statement about
*dependencies*, not about interpreters: Python 3.12 is required throughout.

---

## Quick start

Everything below is deterministic, offline, and requires no credentials.

```bash
handoff version
handoff self-test          # design invariants: positivity, identities, determinism
handoff stages             # declared stages and their guard conditions
handoff baselines          # comparator registry resolution and eligibility
handoff privacy-scan       # fail if tracked files leak private material
handoff doctor             # configuration, compute routing, public/private boundary
```

`self-test` checks properties that must hold for the analysis to mean anything:
that inclusion probabilities sum to `k` exactly and are strictly positive
everywhere, that the decomposition closes with zero residual, that the selection
bias equals its closed form, that the sham sign convention is
mechanism-dependent, and that the allocation solver is order-independent.

---

## Configuration

All configuration comes from the environment; no path belonging to any
particular machine appears in this repository.

| Variable | Meaning |
|---|---|
| `HANDOFF_PRIVATE_HOME` | runtime workspace for data, runs, caches and credentials |
| `HANDOFF_RELAY_MODEL` / `HANDOFF_RECEIVER_MODEL` | exact pinned version strings |
| `HANDOFF_RELAY_PROVIDER` / `HANDOFF_RECEIVER_PROVIDER` | `mock` by default |
| `HANDOFF_TOKENIZER` | frozen tokenizer name |
| `HANDOFF_SOURCE_WINDOW_TOKENS` | relay-visible window |
| `HANDOFF_RELAY_BUDGET_TOKENS` | matched output budget |
| `HANDOFF_MASTER_SEED` | root of all derived seeds |
| `HANDOFF_ALLOW_NETWORK` | off by default |

Credentials are read from the environment only. They are never accepted as
arguments, written to disk, logged, or included in a repr. `handoff doctor`
reports only *whether* a credential is present.

Model identifiers default to `UNFROZEN`, and an unpinned run is a hard error
rather than a silent default: a moving alias would make measurement claims
unreproducible.

See [`.env.example`](.env.example) for the shape of a local environment file.
Keep the real one outside this repository.

---

## Reproducibility

The freeze chain is deliberately acyclic:

1. freeze prompts, specifications, code, support files and source artifacts;
2. hash them into an **artifact manifest**;
3. finalise the pre-registration, which *cites* the manifest hash;
4. create a **freeze record** carrying the pre-registration hash, manifest hash,
   source-pool hash, commit, model versions and a UTC timestamp;
5. verify before running;
6. record every deviation.

There are two records. A **protocol freeze** precedes the discovery stage. A
separate **final-test freeze** additionally binds the sealed test documents,
focal samples, atom inventories, prompts, comparator revisions, the fitted policy
artifact, the feature schema, the renderer, budgets, tokenizer and every analysis
and export script. No final-test runner executes without a valid record.

`handoff manuscript-check` fails if a manuscript still carries unresolved
placeholders, missing generated fragments, or assets absent from the results
manifest. It distinguishes intentionally static conceptual diagrams from
unresolved experimental figures — and it never makes itself pass by inventing
data.

---

## Benchmarking

Comparators are wrapped behind one interface:

```python
compress(source_text, downstream_task, token_budget, config) -> HandoffResult
```

Two invariants are enforced in code rather than trusted:

- **Budget.** Every adapter verifies its realised output against the hard
  ceiling. No method gets a larger effective context because its native
  tokenizer differs.
- **Focal secrecy.** Sampled atom identities and values never enter a compressor
  prompt or configuration. Otherwise focal sampling would become supervision for
  query-aware methods.

Comparators are split by the kind of state they produce. A method whose
compressed state is textual can have atom presence audited by the same frozen
matcher and may participate in the causal comparison. A method whose compressed
state is latent or a cache is **endpoint-only**: literal atom presence is
undefined for hidden states, and the toolkit does not manufacture a substitute
for them.

External methods ship as `NOT_READY` and require their own official
implementations and licences. Bringing one online means cloning the official
repository, pinning an exact revision and checkpoint, and passing a reproduction
gate on a public task before any comparison is produced. A method that fails its
reproduction gate is reported as unreproduced; it is never approximated, and
never swapped out after results are visible.

Comparative claims are governed by a rule that lives in code, with a fixed
denominator and a fixed criterion, evaluated by paired document-clustered
bootstrap. If the criterion is not met, the complete comparison is reported
without comparative language.

---

## Tests

```bash
pytest -q
ruff check .
mypy src
handoff privacy-scan
```

Continuous integration runs deterministic checks only: no credentials, no
private data, no model calls, no external repository clones, no experiments.

---

## Project status

Early. The measurement, estimation, provenance and export machinery is
implemented and covered by deterministic tests against synthetic fixtures. The
experimental protocol is written but **not yet executed**: no corpus has been
acquired, no model has been pinned, and no result exists.

Accordingly this repository makes **no empirical claims of any kind**. Comparator
adapters are declared but not bound to implementations, and several protocol
values are marked `PROPOSED` pending approval rather than silently frozen.

---

## Repository layout

```text
src/handoff_fidelity/
  corpus/        section extraction, normalisation, source frame + hashing
  atomizer/      rule-based Tier-1 extraction, verification, eligibility
  sampling/      role-stratified design and inclusion probabilities
  matcher/       canonicalisation, token-boundary matching, validation
  editing/       availability editor, sham edits, invariance checks
  relay/         the frozen global downstream task
  receiver/      slot schemas and the single shared receiver prompt
  interventions/ matched skeleton, prior probe, budget-neutral swaps
  causal/        estimands, weighting, sham regions, targeting, gates, multi-hop
  causalrelay/   features, model, renderer, allocation
  baselines/     adapter API, controls, registry, external adapters
  benchmark/     orchestration, reproduction gate, comparison rule
  inference/     document-clustered bootstrap
  provenance/    hashing, manifests, freeze records, results manifest
  export/        table fragments, figures, manuscript guard
  stages/        stage specifications and execution guards
  compute/       device routing
  privacy/       repository scan and public/private boundary
docs/            design, estimands, protocol, reproducibility, architecture
configs/         comparator registry, example configs, schemas
tests/           deterministic tests over synthetic fixtures only
```

---

## Citation

See [`CITATION.cff`](CITATION.cff). The metadata is intentionally minimal while
the associated write-up is unpublished.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Two rules matter more than the rest:
no result may be entered by hand into an exported artifact, and no comparator may
be added or removed on the basis of how it performs.

## Licence

MIT. See [`LICENSE`](LICENSE).
