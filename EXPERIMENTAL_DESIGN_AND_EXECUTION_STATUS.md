# Experimental Design and Execution Status

**Project:** Transmission vs Reconstruction / Handoff Fidelity  
**Manuscript:** v2.7 scientific architecture frozen  
**Execution protocol:** under pre-run hardening; not yet binding  
**Experimental model calls:** should not begin until the final protocol bundle is validated and frozen

---

## 1. Scientific question

A downstream LLM can state a fact correctly even when the upstream relay never transmitted it. The receiver may reconstruct the missing information from remaining context or parametric knowledge.

The project asks:

> **How much endpoint correctness is caused by information that genuinely survived the handoff, and how much is reconstruction after omission?**

This matters because reconstruction and transmission can look identical on familiar data but fail differently under domain shift, unusual values, new entities, or changing receivers.

---

## 2. Core causal quantities

For focal atom `z` and the natural non-focal relay content `M_obs,-z`:

- `T_z ∈ {0,1}` — whether the natural relay transmitted the atom;
- `R^-_z` — receiver recovery with the focal atom unavailable and natural non-focal content held fixed;
- `D^+_z` — receiver recovery with the focal atom available;
- `Δ_z^avail = D^+_z - R^-_z` — causal availability surplus;
- `A` — observed endpoint fidelity.

The natural decomposition is

```text
A = R̄₀ + T̄ Δ̄ + Cov(T, Δ)
```

where:

- `R̄₀` = focal-omission reconstruction baseline;
- `T̄ Δ̄` = communication volume × average availability value;
- `Cov(T,Δ)` = assignment–effect / targeting alignment.

The algebra is elementary; the contribution is causal identification and measurement.

---

## 3. Why observational omission is insufficient

A relay decides what to omit. It may preferentially omit predictable/recoverable facts. Therefore studying only naturally omitted atoms gives a selected sample.

The observational reconstruction quantity

```text
R_obs = E[R^- | T=0]
```

need not equal the target population baseline `R̄₀`.

The paper's intervention is designed to recover the missing causal arm while preserving the natural message on the observed side.

---

## 4. Experiment A — natural relay decomposition

### Goal

Estimate reconstruction, explicit-transmission value, assignment–effect alignment, and observational-selection bias in the natural workflow.

### Planned unit

A verified Tier-1 factual atom from the **exact source text shown to the relay**.

Primary Tier-1 roles:

- entity;
- scope;
- period;
- numeric;
- provenance.

### Procedure

1. Build exact relay-visible source `X_i`.
2. Create/verify `Z(X_i)` from the same source.
3. Select focal atoms before relay generation using a positive-probability fixed-size stratified design.
4. Run the natural relay once under the frozen budget `B`.
5. Detect `T_iz` by the frozen canonical matcher.
6. Query the receiver on the **unaltered natural message**.
7. Create only the counterfactual side:
   - if `T=1`: construct `M^-z`;
   - if `T=0`: construct `M^+z`.
8. Hold non-focal message content fixed.
9. Query the receiver.
10. Compute `R^-`, `D^+`, `Δ^avail` under the decoder regime specified in the preregistration.
11. Aggregate using design weights.
12. Report edit-placebo/sensitivity diagnostics and exclusion rates.

### Critical validity requirements

- focal selection cannot depend on relay output;
- every target atom needs positive inclusion probability;
- focal atoms must be inside relay-visible source text;
- natural observed message must remain natural;
- deletion/insertion cannot silently change non-focal content;
- intervention infeasibility must not create unreported post-treatment selection.

---

## 5. Experiment B — matched prior-access contrast

### Goal

Determine how much reconstruction is assisted by receiver priors rather than transmitted evidence.

### Why a natural-vs-randomized relay comparison is insufficient

Randomizing identities/values can change what the relay chooses to transmit, which changes non-focal context. Then a reconstruction difference mixes:

1. prior accessibility; and
2. changed context composition.

### Identification design

Use a **fixed non-focal skeleton** `H_-z`:

- focal target absent in both arms;
- same slots/structure/length outside the intended mapping;
- natural identity/value mapping in one arm;
- controlled prior-blocked mapping in the other.

The paired contrast is the primary Experiment-B quantity.

### Auxiliary prior probe

A separate closed-book probe measures prior recoverability under standardized identity/framing context. It is secondary and must use fresh contexts. The manuscript no longer depends on a fragile continuous regression on a noisy prior score.

### Still to lock

The preregistration bundle must freeze an executable context-tuple construction so the skeleton uses genuinely related source atoms rather than arbitrary values pulled from a document-level inventory.

---

## 6. Experiment C — post-gate budget-neutral targeting

### Goal

Test whether a relay allocates scarce message budget toward atoms for which explicit transmission has high value.

### Important distinction

`Δ^avail` from Experiment A permits focal insertion without evicting another atom. It cannot be used as a fixed-budget effect.

Experiment C therefore estimates `Δ^budget` using matched-length insert/evict swaps.

### Fully instrumented subset

For a smaller predeclared subset:

1. enumerate the Tier-1 candidate set;
2. instrument every candidate atom;
3. estimate individual `Δ^budget`;
4. compute first-order allocation metrics.

### Additivity caveat

The first-order utility

```text
G(t) = Σ_z v_z t_z Δ_z^budget
```

is **not** automatically the true joint causal utility because atoms can interact/redundantly encode information. It is treated as a first-order benchmark. A pairwise interaction diagnostic determines whether “oracle” language remains appropriate.

### Status

Post-gate only. It should not block Experiments A/B.

---

## 7. Multi-hop extension

If Stage 1 supports the core effect, repeat at depths:

```text
h ∈ {1, 2, 3, 5}
```

The key hypothesis is not a generic information-theoretic monotonicity claim. The empirical question is whether:

- transmitted content changes across depth;
- reconstruction baseline changes;
- endpoint fidelity remains deceptively high despite deterioration in genuine transmission.

---

## 8. Stage structure and discovery gate

### Stage 1

Planned:

- 100 documents;
- 3 focal atoms per document;
- 300 primary focal units before intervention exclusions.

### Stage 2

If Stage 1 passes:

- 300 **new**, disjoint confirmatory documents;
- no reuse of Stage-1 documents unless explicitly changed before freeze.

### Planned effect-size gates

Proceed if either:

```text
matched prior-access effect >= 0.10
```

on a predeclared eligible class, or

```text
E[(1-T)R^-] >= 0.10
```

Halt if both fail.

These are discovery effect-size gates, not p-value gates.

---

## 9. Sampling design

The correct target design is fixed-size role-stratified sampling without replacement.

For a document with `m_i >= 3` populated strata:

1. uniformly select 3 distinct populated strata without replacement;
2. uniformly select 1 atom from each selected stratum.

For atom `z` in selected stratum `s` of size `n_is`:

```text
π_iz = (3 / m_i) * (1 / n_is)
```

Every eligible atom then has positive first-order inclusion probability, and the inclusion probabilities sum to `k=3` within a document.

The implementation in this repo includes tests for this invariant.

---

## 10. Edit placebo and sensitivity

A sham edit is a **mechanical negative control**, not proof of edit neutrality.

The edit-bias model belongs on the receiver-mean scale. Mechanical effects are estimated separately for insertion/deletion; residual semantic edit effects are propagated through a sensitivity/partial-identification region rather than assumed zero.

The final preregistration must freeze:

- sham sampling rate;
- sensitivity grid;
- intervention-failure cap;
- differential failure cap by `T`/mechanism;
- handling of ineligible focal atoms;
- no post-hoc focal replacement after observing `T` or outcomes.

---

## 11. Source population

### Primary domain

SEC 10-K Management Discussion & Analysis (MD&A) text.

### Required source workflow

The source frame and atomization frame must be separated:

1. metadata/extraction-only candidate source frame;
2. CIK-level split into calibration and experimental candidates;
3. freeze/validate atomizer on calibration material only;
4. apply frozen atomizer + human verification to stage candidates;
5. require Tier-1 atom/strata eligibility on the **exact relay-visible truncated source**;
6. produce final source pool;
7. seed-select Stage 1 and Stage 2.

### Still requires real execution

- retrieving/fixing the SEC source snapshot;
- human verification of extracted MD&A and atom inventories;
- final source-pool hash.

These require external data access and cannot be truthfully completed inside an offline artifact-generation session.

---

## 12. Receiver/relay model regime

### Primary causal receiver

The paper supports a deterministic regime `(D)` and a stochastic regime `(S)`. The current planned pilot prefers `(D)` if the selected provider/model is operationally reproducible.

Temperature `0` and a seed do **not** by themselves guarantee determinism for all providers. Before Stage 1:

- pin exact provider/model/version;
- run repeatability checks on a disjoint calibration set;
- if exact structured outputs are not stable, switch/re-register under `(S)` rather than pretending `(D)` holds.

### Provider adapters

This repository provides optional adapters/scaffolding for:

- OpenAI;
- Anthropic;
- Gemini;
- local Hugging Face models.

No default production model is silently chosen. Exact models belong in the final preregistration/freeze record.

---

## 13. Public/private data boundary

### Public

```text
~/Desktop/My_Git/transmission-vs-reconstruction
```

Safe for GitHub:

- code;
- docs;
- tests;
- public protocol artifacts;
- no credentials/private raw data.

### Private

```text
~/Desktop/handoff-fidelity
```

Never a Git repo. Stores:

- `.venv-handoff-fidelity`;
- `.env` / API keys;
- raw data;
- run outputs;
- calibration files;
- private freeze artifacts;
- caches/logs.

The public package is installed editable into the private venv.

---

## 14. What is implemented in this generated repository

### Implemented now

- modern `src/` Python package;
- Typer CLI;
- public/private path guard;
- Pydantic configuration/types;
- fixed-size positive-probability focal sampling;
- canonical Tier-1 matcher utilities;
- conservative message editor primitives;
- deterministic decomposition/selection-bias estimators;
- Stage gate logic;
- document-cluster bootstrap helper;
- SHA-256 artifact-manifest/freeze verification;
- mock provider for no-network tests;
- optional API/local-provider adapter scaffolding;
- Stage-1 dry-run guard;
- macOS private-workspace/bootstrap script;
- Colab/A100 template;
- GitHub CI and pre-commit setup;
- design self-tests.

### Deliberately not claimed complete

The following require final scientific/human decisions or external execution:

- binding preregistration v1.2+;
- exact relay/receiver model/version strings;
- final relay token budget `B`;
- final prompts after professor review;
- exact source snapshot/pool;
- human atomizer and matcher validation;
- Experiment-B context-tuple policy validation;
- operational deterministic-decoder audit;
- actual no-evidence chance baselines;
- actual API/open-weight model calls;
- Stage-1/Stage-2 result generation;
- qualitative human adjudication;
- paper result tables/figures populated from real outputs.

---

## 15. Division of labor: ChatGPT vs Claude/Antigravity vs actual compute

### What this generated repo can safely provide

Code architecture, deterministic mechanics, tests, protocol integrity tooling, dry-run orchestration, analysis/statistics utilities, documentation, and reproducible setup.

### Good use of Claude or Antigravity before freeze

- code review against the manuscript/preregistration;
- finalize detailed prompt wording;
- verify source extractor/atomizer implementation;
- inspect Experiment-B matched-skeleton construction;
- adversarially review tests and protocol invariants;
- populate manuscript figures/tables after real results.

They should not silently change the design or make outcome-informed protocol decisions.

### Must be done as actual runs

On the user's infrastructure with real source data/provider credentials:

- SEC retrieval/source freezing;
- provider/model pinning;
- calibration calls;
- determinism audit;
- prior-probe calls;
- natural/counterfactual receiver calls;
- Stage 1;
- Stage 2;
- depth/Experiment-C extensions.

### MacBook Pro M4 Pro

Recommended default coordinator for Stage 1, especially when relay/receiver are APIs. Use MPS only for compatible small local-model checks.

### Colab Pro A100

Use when inference is performed with open-weight CUDA models or when high-throughput repeat sampling/depth sweeps benefit from GPU compute. API-only experiments gain little from the A100 itself.

---

## 16. Recommended next sequence

1. Professor reviews experimental design.
2. Finalize preregistration v1.2+ and executable prompt/spec bundle.
3. Freeze exact source frame.
4. Pin relay/receiver models.
5. Run calibration-only validation.
6. Finalize artifact manifest and freeze record.
7. Verify the freeze mechanically.
8. Run the 100-document Stage-1 pilot without inspecting partial outcomes.
9. Compute gates/intervals.
10. Proceed/stop exactly as preregistered.
11. Only then run Stage 2 and post-gate extensions.

---

## 17. Current bottom line

The **scientific causal architecture is frozen**, but the **experimental implementation is not yet legally/scientifically “sealed.”** The remaining work is not another theoretical redesign; it is the disciplined conversion of the design into an executable, audited, preregistered protocol before the first real experimental result exists.
