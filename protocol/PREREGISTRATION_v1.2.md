# Pre-registration v1.2

**Status: DRAFT — NOT YET BINDING.**

This document becomes binding only when every field marked `[ ]` carries a real
value, the artifact manifest has been built, this file has been hashed, and a
freeze record has been written. Until then it is a design contract, not a
commitment.

Values marked **PROPOSED** are not approved. They are written down so that a
reviewer can approve or reject them explicitly, rather than discovering later
that a number was frozen silently.

Supersedes v1.1. Section 20 lists every change from v1.1 and why. The v1.1 hash
is void as a commitment.

---

## S1. Integrity

| Field | Value |
|---|---|
| Pre-registration version | v1.2 |
| Authored (UTC) | [ ] |
| Frozen (UTC) | [ ] |
| Artifact manifest SHA-256 | [ ] |
| Source-pool SHA-256 | [ ] |
| Code commit | [ ] |

The hash chain is acyclic: this document cites the artifact manifest hash; the
freeze record cites this document's hash. Nothing cites the freeze record.

---

## S2. Source population

- **Primary domain:** management discussion and analysis sections of annual
  reports, chosen for density of canonically valued Tier-1 atoms.
- **Vintage:** older, widely public filings for the natural arm, so that
  parametric prior access can exist at all. A receiver with no exposure to the
  entity would collapse the natural and randomised arms and destroy the
  Experiment-B contrast.
- **Unit:** one document per issuer, most recent qualifying filing.
- **Licence:** public-domain government filings only.
- **Inclusion filter:** the section boundary must be located deterministically;
  the extracted span must exceed 500 characters; the document must yield at
  least `k = 3` populated eligible strata.
- **Retrieval:** no retrieval has been performed. `SOURCE_POOL.csv` ships
  header-only with a deterministic builder whose retrieval block is an explicit
  integration point.

---

## S3. Relay-visible source frame

This is the structural core of the protocol.

```
raw -> section extraction -> normalisation -> frozen tokenizer
    -> window cut -> SHA-256 -> atomize THAT text
```

| Field | Value | Status |
|---|---|---|
| Source window `L` | 2000 tokens | **PROPOSED** |
| Tokenizer | `cl100k_base` | frozen |
| Truncation | hard, at `L` | frozen |
| Frame hash | SHA-256 of the exact windowed text | frozen |

**Inventory equivalence.** The atomizer, the eligibility filter, the focal
sampler and *every compressor* operate on exactly the frame text. No atom may
exist outside relay-visible content, because an atom the compressor never saw
cannot be a transmission failure. This is checked mechanically per document, not
assumed.

---

## S4. Atom inventory

**Tier-1 only:** entity, scope/segment, period, numeric, provenance reference.
Tier-2 (relation strength, certainty, counterevidence) is paraphrasable, so both
presence detection and minimal editing would become model-mediated, putting a
judge inside the primary outcome. Tier-2 is a post-gate extension.

- **Extraction:** deterministic and rule-based. No model is used.
- **Overlap resolution:** longest span wins; ties by frozen role order, then
  start offset. Total and deterministic, so the inventory does not depend on
  iteration order.
- **Duplicate merge:** by `(role, canonical_value)`, retaining span multiplicity
  in `occurrence_count`. Deletion must remove **every** canonical-equivalent
  occurrence.
- **Conflict groups:** the same canonical value claimed by more than one role in
  a document makes presence ambiguous and the edit ill-defined. Excluded
  pre-treatment.
- **Human verification:** blocking. Rows without an explicit decision are not
  admitted; they are never defaulted to accepted.
- **Agreement:** Cohen's kappa `>= 0.70` on the calibration set. **PROPOSED.**
- **Calibration disjointness:** the calibration pool is disjoint from every
  experimental split by issuer.

Target population wording, to be used verbatim in any write-up: *the
human-verified Tier-1 inventory produced by the frozen atomization procedure
applied to the relay-visible source frame*.

---

## S5. Focal sampling

For a document with `m_i` populated eligible strata:

```
require m_i >= k,  k = 3
choose k strata uniformly WITHOUT replacement from ALL populated strata
choose one atom uniformly within each selected stratum
pi_iz = (k / m_i) * (1 / n_is)
```

Consequently `Σ_z π_iz = k` exactly and `π_iz > 0` for every atom in the
eligible inventory.

**This corrects a defect in v1.0.** The earlier rule sampled the `k` most
populated strata, giving `π = 0` off-support. That does not merely violate
positivity — it leaves the Hájek estimator undefined on part of the target
population.

- Sampling occurs **before** the relay runs.
- Focal identities are never shown to any compressor.
- Documents with `m_i < k` are ineligible and excluded pre-treatment.
- Seeds derive from the master seed plus a stage label.

| Field | Value | Status |
|---|---|---|
| `k` | 3 | frozen |
| Master seed | 20260907 | frozen |

---

## S6. Relay, receiver and decoding

| Field | Value | Status |
|---|---|---|
| Relay model version | [ ] | **must be pinned** |
| Receiver model version | [ ] | **must be pinned** |
| Decoder regime | (D) primary, (S) robustness | frozen |
| Output budget `B` | 500 tokens (25% of `L`) | **PROPOSED** |
| Budget sweep | 100 / 50 / 25 / 10 % | **PROPOSED** |

A moving alias would make the study unreproducible, which is indefensible in a
measurement-validity project. `UNFROZEN` is a hard error at run time.

**Determinism audit.** Regime (D) is permitted only after an operational audit:
the same request, the same configuration, repeated on **disjoint calibration
prompts**, must agree **exactly**. Temperature zero is not evidence. If
agreement is not exact, either switch receiver or issue a revised
pre-registration under regime (S) — under which atom-level statistics that are
nonlinear in the surplus are not identified from one query per availability.

| Field | Value | Status |
|---|---|---|
| Audit prompts | 50 | **PROPOSED** |
| Repeats per prompt | 5 | **PROPOSED** |
| Required agreement | exact, 1.00 | frozen |

---

## S7. Receiver prompt and slot schema

**One shared receiver prompt** is used for the natural arm, the counterfactual
arm, both matched-skeleton arms and the no-evidence baseline. Different prompts
across arms would confound a prompt difference with the availability contrast.

The prompt instructs the receiver to answer from the note and, if the note does
not state the answer, to give its best single answer anyway. Refusal would
conflate "did not reconstruct" with "declined to answer".

Per-class slots are frozen and each requires a subject and an attribute. A probe
must reveal enough identity and context to ask a well-defined question while
withholding the focal value. Bare prompts of the form `Numeric = ?` are
forbidden.

---

## S8. Availability intervention

| observed | constructed | mechanism |
|---|---|---|
| `T = 1` | delete every canonical-equivalent occurrence | `del` |
| `T = 0` | insert the rendered atom | `ins` |

- The natural message is **never** edited.
- Insertion **overruns** the budget rather than displacing; the overrun
  distribution is reported. Under overrun a negative surplus isolates
  interference and cannot be a displacement artefact.
- Insertion position is frozen: a new final line. Any content-sensitive
  placement would put a judge inside the intervention.
- **Non-focal invariance** is checked on every edit: masking all
  canonical-equivalent occurrences in both messages and collapsing whitespace
  must leave identical strings.
- Deletion is refused for entangled clauses. Insertion is refused if the matcher
  cannot detect the rendered atom, since renderer and matcher must agree.
- Failed edits are logged and reported, never silently dropped.

**Intervention-failure invalidation.**

| Trigger | Threshold | Status |
|---|---|---|
| Overall intervention-failure rate | > 15% | **PROPOSED** |
| Differential failure between `T=1` and `T=0` | > 10 points | **PROPOSED** |

The second trigger matters independently: differential eligibility by arm
reintroduces precisely the selection this design exists to remove.

---

## S9. Matcher

Deterministic normalised matching per role, with **token-boundary** semantics.
Substring matching is forbidden: it reports an entity as present inside a longer
name and a period inside a longer period, inflating `T`.

Handled: Unicode normalisation, case, whitespace, punctuation, percentages,
thousands separators, decimal equivalence by exact decimal arithmetic, currency
magnitude words, and period formats.

**Validation gates — both blocking:**

| Gate | Value |
|---|---|
| Precision | `>= 0.95` |
| Recall | `>= 0.95` |
| Audit sample | 200, stratified **100 presence / 100 absence** |
| Blinding | the matcher's prediction is withheld from the auditor |

Recall is blocking alongside precision because a matcher that rarely fires would
pass a precision-only gate while systematically understating `T`. Stratification
is required because a simple random 200 would estimate recall on however many
presence cases happened to land.

Matcher error is propagated into downstream intervals.

---

## S10. Sham-edit placebo

Two shams, estimated separately, because deletion and insertion are different
operations with different artefact profiles.

- **Deletion sham:** replace every occurrence with an equivalent surface form
  that canonicalises to the same value.
- **Insertion sham:** append a rendered line carrying content already present.
- The sham subset is drawn independently of `T`.

| Field | Value | Status |
|---|---|---|
| Sham rate | 0.20 of focal atoms | **PROPOSED** |
| Reported `epsilon_bar` grid | 0.00, 0.02, 0.05, 0.10 | **PROPOSED** |

Sign convention: `s = 2T − 1`, so `Δ = Δ̂ + s·ε_m`. A common offset applied to
both mechanisms would double-count on one arm and cancel on the other.

The primary analysis is the **population** partial-identification region. The
point correction is secondary and carries its assumption at every use. The
placebo is a negative control on the mechanical artefact only; it cannot
establish the exclusion restriction, and claiming otherwise would be an
overstatement.

---

## S11. Experiment B — matched skeleton

- Tuples are drawn from a frozen bounded local window (same sentence).
- **Minimum three populated roles.** All five are not required: that would
  exclude most real sentences and silently redefine the population.
- The focal slot renders as `<<OMITTED>>` in **both** arms.
- Only the identity–value mapping differs; slot structure, order, position and
  the intended length rule are identical, asserted mechanically.
- `T̄_nat − T̄_blk` is a **manipulation check only** and plays no role in
  identification.

### Randomised supports

| Class | Support | `K_eff` | Status |
|---|---|---|---|
| entity | 200 generated fictitious names | 199 | **PROPOSED**; additionally blocked on human screening against a real-issuer registry, which has not been performed |
| scope | frozen segment/geography list | `|S| − 1` | frozen |
| period (annual) | 6 | 5 | frozen |
| period (quarter) | 24 | 23 | frozen |
| numeric (`pct` only) | plausible range, 2 decimals | stated per document | **PROPOSED** |

Only the `pct` numeric subtype is randomised. Currency magnitudes are not
exchangeable across issuers, so a uniformly redrawn currency value would not be a
plausible counterfactual.

`K_eff = |support| − 1` because the natural value is excluded from its own
redraw. Reporting `1/|support|` would understate chance.

**Chance is reported two ways:** the nominal `1/K_eff`, and the **empirical
no-evidence baseline** obtained by querying the receiver with the slot and no
evidence. The empirical baseline is operative, because a receiver free to answer
outside the candidate set matches with probability `P(output ∈ K)/K ≤ 1/K`.

A pooled chance level across classes is never reported.

---

## S12. Prior probe

Auxiliary, and separate from the pinned causal receiver.

| Field | Value | Status |
|---|---|---|
| Option | (B) stochastic, fresh context | frozen |
| `m_prior` | 10 | **PROPOSED** |
| Bins | low `[0, 1/3)`, medium `[1/3, 2/3)`, high `[2/3, 1]` | **PROPOSED** |
| Order-invariance check subset | 50 atoms | **PROPOSED** |
| Fallback | (A) binary under (D) if the probe budget is unavailable | frozen |

One focal atom per query. Probes never run in the same context as Experiment A
or B.

The dose–response is reported as a **reliability-aware stratification**, not as a
slope on a mismeasured regressor. Bin width `1/3` is large relative to the
worst-case binomial standard error at `m_prior = 10`. That bin assignment is
itself noisy, which attenuates the trend, is stated with the result.

---

## S13. Estimation and inference

- Default estimator: **Hájek**. Horvitz–Thompson is reported where the
  population size is known.
- Two-phase weighting with `q_iz > 0` is supported; the pilot sets `q ≡ 1` for
  precision, not necessity.
- Stratum-specific and weighted pooled estimates are both reported. An
  unweighted pooled number is never reported alone.
- Intervals: document-clustered nonparametric bootstrap, **10,000 replicates**
  for final reporting. `n` is reported in documents.
- Paired method comparisons resample a common document draw.

---

## S14. Stage 1 gate

```
matched prior-access effect >= 0.10 on a predeclared eligible class
                             OR
reconstruction contribution E[(1-T)R^-] >= 0.10
proceed if either clears; halt only if both fail
```

| Field | Value | Status |
|---|---|---|
| Eligible prior classes | scope, period, numeric | **PROPOSED** |
| Both thresholds | 0.10 | frozen |
| Stage 1 documents | 100 | frozen |

An **effect-size discovery threshold, not a significance test**. No p-value gates
any decision, and no post-hoc threshold adjustment is permitted. A low
reconstruction rate in the randomised arm alone is the manipulation working, and
is not grounds to halt.

---

## S15. Stage 2 and the benchmark

| Field | Value | Status |
|---|---|---|
| Development documents | 100 | **PROPOSED** |
| Sealed test documents | 200 | **PROPOSED** |
| Stage 1 / Stage 2 overlap | none | frozen |
| Issuer disjointness | required where feasible | frozen |
| Test manifest | immutable after the test freeze | frozen |

Development data may be used only to calibrate comparator budget adapters and to
fit the relay policy. Test documents are used exactly once.

### Comparator suite

Primary (counts toward the criterion): four textual compressors whose compressed
state is auditable by the frozen matcher. A legacy anchor is reported but never
counts. Latent/cache methods are endpoint-only.

Each primary comparator must pass the reproduction gate on a public or native
task before entering: install, checkpoint load, native example, textual output,
budget adapter, and a published metric reproduced within **2 percentage points**
or overlapping the published interval. Failure is reported as unreproduced.

### Comparative criterion

At the matched budget, at least **three** primary comparators must satisfy
**both** `lower_95CI(ΔA) > 0` and `lower_95CI(ΔC_comm) > 0`.

If the criterion fails: publish the full comparison without comparative
language. No comparator deletion, no substitution, no metric change.

---

## S16. The relay policy

- Fitted on **development documents only**.
- Target: budget-neutral surplus on the predeclared candidate set.
- Features: frozen, pre-treatment, source-side only. Forbidden features are
  rejected in code by name.
- Family: gradient-boosted regressor primary, ridge ablation. **PROPOSED.**
- Hyperparameters by **grouped cross-validation by document**. Atom-level folds
  would leak, since atoms in a document share one relay realisation.
- Allocation: deterministic, over `max(0, ŝ)`, with frozen tie-breaking.
- Renderer: deterministic, non-model, and **shared with the uniform-atoms
  control**, so the comparison isolates allocation rather than presentation.
- Test outcomes, interventions and oracle labels never touch allocation.

---

## S17. Experiment C

Post-gate. A predeclared, smaller, **fully instrumented** subset.

Every member of the candidate set receives a matched-length swap; `G*` requires
`Δ^bu` for the whole feasible set, so sample splitting is incoherent here.

`G*` is the **first-order surplus benchmark**, not the true causal optimum. A
pairwise interaction diagnostic decides whether the additivity reading stands;
if interactions are large the oracle is dropped and only `Cov(T, Δ^bu)` is
reported. `η_U` is undefined when `G* ≤ G_rand` and reported as such.

| Field | Value | Status |
|---|---|---|
| Subset size | [ ] | **PROPOSED** |
| Eviction length tolerance | 2 tokens | **PROPOSED** |
| Interaction pairs sampled | [ ] | **PROPOSED** |
| Interaction threshold | 0.25 of mean abs surplus | **PROPOSED** |

---

## S18. Multi-hop

Depths 1, 2, 3, 5. Post-gate. `A^(h)` and `T̄^(h)` are always plotted together.

**No monotonicity is enforced.** A receiver that reconstructs an atom at hop `h`
may cause it to be transmitted at hop `h+1`, so `T̄^(h)` can rise. No
data-processing claim is made.

---

## S19. Exclusions and reporting

Reported separately, each as a rate: atomizer failure, conflict groups, entangled
surface forms, unverified atoms, invalid edits, coherence-audit failures, missing
eviction partners, and documents with fewer than `k` populated strata.

All exclusions are decided pre-treatment.

---

## S20. Changes from v1.1

**Corrections.**

1. Focal sampling stated as uniform-without-replacement over **all** populated
   strata, with `π = (k/m)(1/n_s)`. v1.1's rule gave `π = 0` off-support.
2. Presence detection specified as token-boundary aware. Substring matching
   inflates `T`.
3. Matcher recall made blocking, and the audit sample stratified
   100 presence / 100 absence.
4. Chance reference changed to `1/K_eff`.
5. `period` split into separate annual and quarterly supports, preserving
   granularity.
6. Sham correction stated with the mechanism-dependent sign `s = 2T − 1`.
7. The atom inventory tied to the relay-visible frame, with a mechanical check.
8. The receiver prompt made a single shared artifact across all arms.
9. Prior probe fixed at one focal atom per query with a well-defined slot.
10. Experiment-B tuples require three populated roles, not five.
11. A differential intervention-failure trigger added alongside the overall cap.
12. The hash chain made explicitly acyclic.

**Still unresolved, and blocking.** Model version strings; the source pool;
instrument validation; human screening of the entity support; and every value
marked **PROPOSED**.

---

## S21. Signature

This pre-registration is not binding until signed with a real timestamp, a real
artifact-manifest hash and a real commit.

| Field | Value |
|---|---|
| Approved by | [ ] |
| Approval date (UTC) | [ ] |
| This document's SHA-256 | [ ] (computed after all blanks are filled) |
