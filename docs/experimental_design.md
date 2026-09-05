# Experimental design

Three interventions, because no single experiment answers every question without
confounding.

## Order of operations

The ordering is a requirement, not a convenience, and it is the single most
easily violated step in an implementation:

```
raw source
  -> extract section
  -> normalise
  -> tokenize with the frozen tokenizer
  -> cut the relay-visible source window
  -> hash that text
  -> atomize THAT text
  -> human verification
  -> pre-treatment eligibility filtering
  -> FOCAL SAMPLING
  -> run the relay
  -> observe T
```

Two properties follow.

**The atom inventory equals the relay-visible frame.** If the atomizer ran on the
full document while the relay saw a window, atoms outside the window would be
scored as transmission failures for content the compressor was never shown. The
toolkit checks this mechanically rather than trusting it.

**Focal sampling precedes the relay.** Drawing focal atoms from the *message*
makes the selection indicator a function of `T` and conditions on `T = 1`. The
stratum `{T = 0}` is then never sampled, `Cov(T, Δ)` is undefined, and the
decomposition collapses.

## Sampling design

For a document with `m_i` populated eligible strata:

- require `m_i ≥ k`, with `k = 3`;
- choose `k` strata uniformly **without replacement from all populated strata**;
- choose one atom uniformly within each selected stratum;
- record `π_iz = (k / m_i) · (1 / n_is)`.

Then `Σ_z π_iz = Σ_s n_is · (k/m_i) · (1/n_is) = k` exactly, and every atom in
the eligible inventory has `π > 0`.

Positivity is the point. A design that took "the `k` most populated strata" gives
`π = 0` off-support, which does not merely violate an assumption — it leaves the
Hájek estimator **undefined** on part of the target population. The self-test
verifies both properties over randomised inventories.

Documents with fewer than `k` populated eligible strata cannot support the design
and are excluded before the relay runs.

## Experiment A — natural relay decomposition

The primary intervention is an **artifact** intervention: minimally edit the
natural message so the focal atom becomes available or unavailable, with the
rest of the message held fixed.

The estimand is the marginal communication value of availability in an otherwise
fixed handoff. It is **not** the message a relay would have produced had it
chosen to omit the atom — that is a policy-level counterfactual, reported only as
sensitivity, because the relay may compensate elsewhere.

Only the missing arm is constructed:

| observed | constructed | mechanism |
|---|---|---|
| `T = 1` | delete the focal atom | `del` |
| `T = 0` | insert the focal atom | `ins` |

The natural message is never edited.

**Insertion overruns the budget rather than displacing.** Under overrun no atom
is evicted, so a negative surplus isolates interference and cannot be a
displacement artefact. Displacement is a separate estimand.

Every edit is checked for **non-focal invariance**: masking every
canonical-equivalent occurrence of the focal atom in both messages and collapsing
whitespace must leave two identical strings. Edits that fail are rejected and the
rate is reported, never silently dropped.

## Experiment B — matched prior-access contrast

A fixed skeleton is shared by a natural and a value-randomised arm, with the
focal atom absent in **both**.

Construction rules:

- tuples are drawn from a frozen bounded local window, so they are relationally
  coherent;
- **not all five roles are required.** Requiring all five would exclude most real
  sentences and silently redefine the population. The minimum is three populated
  roles;
- the focal slot renders as `<<OMITTED>>` in both arms;
- only the identity–value mapping differs. Slot structure, order, position and
  the intended length rule are identical, and this is asserted mechanically.

The transmission-rate difference between arms plays **no role in
identification** — the skeleton is fixed — and is reported purely as a
manipulation check on how far randomisation perturbs relay behaviour.

### Prior probe

Auxiliary and separate from the causal receiver. The pinned deterministic
receiver returns only `{0,1}` from one closed-book probe, which is too coarse for
a dose–response, so the probe uses stochastic decoding over `m_prior` independent
**fresh-context** draws.

One focal atom per query. A batched autoregressive vector would let earlier slots
condition later ones, so the probe would partly measure self-conditioning rather
than prior access.

A probe must reveal enough identity and context to ask a well-defined question
while withholding the focal value. Prompts of the form `Numeric = ?` are
forbidden: they measure prompt ambiguity.

The resulting proportion is a **mismeasured regressor** with binomial variance.
Regressing on it attenuates the slope toward zero, so the analysis does not
depend on an errors-in-variables model: the primary result is the matched
contrast, which involves no probe regressor at all, and the dose–response is
secondary, reported as a reliability-aware stratification across pre-registered
bins whose width is large relative to the binomial standard error. That bin
assignment is itself noisy — which attenuates the observed trend — is stated with
the result rather than corrected away.

### Chance levels

In the randomised arm a focal value is drawn from a class-specific support. If
the response space is constrained to that set, guessing succeeds with probability
`1/K_eff`. If the receiver may answer outside it, `1/K_eff` is a **nominal upper
bound** rather than the operative chance level, so the **empirical no-evidence
baseline** — the same slot with no evidence at all — is what reconstruction is
judged against.

`K_eff = |support| − 1` when the natural value belongs to the support, because
the natural value is excluded from its own redraw. Reporting `1/|support|` would
understate chance.

`K` differs sharply by class, so a pooled chance level is not interpretable and
is never reported.

## Experiment C — budget-neutral targeting

Post-gate only, on a predeclared, smaller, **fully instrumented** subset.

Sample splitting does not work here: computing `G*` requires `Δ^bu` for every
candidate in the feasible set, which a held-out half does not supply, and two or
three focal atoms per document are far too few to define a document-level
allocation problem.

For each document the candidate set is the complete enumeration of atoms that
pass the atomizer, admit a matched-length counterpart for eviction, and survive
the coherence audit under both insertion and eviction. Every member receives a
matched-length swap.

`η_U` is undefined when `G* ≤ G_rand` and is reported as such, never imputed.
Ties in the allocation solver are broken deterministically and the tie rate is
reported.

## Sham-edit placebo

A semantics-preserving edit applies the editing machinery while leaving the
focal atom's meaning intact, isolating formatting disruption, fluency loss,
length change and position shift.

Two shams, not one: deletion and insertion are different operations with
different artefact profiles, and there is no reason for their artefacts to
cancel.

The sham subset is drawn independently of `T`. A null placebo is demonstrated,
never assumed.

## Stages

| Stage | Documents | Status |
|---|---|---|
| Calibration | instrument validation only | frozen |
| Stage 1 | 100, mechanism discovery | frozen |
| Stage 2 development | 100 | **PROPOSED** |
| Stage 2 sealed test | 200 | **PROPOSED** |
| Experiment C | subset | **PROPOSED** |
| Multi-hop | depths 1, 2, 3, 5 | **PROPOSED** |

No Stage-1 document may appear in Stage 2, and splits are issuer-disjoint where
feasible. Development and test manifests are immutable after the test freeze.

### Discovery gate

```
matched prior-access effect  >= 0.10  on a predeclared eligible class
                              OR
reconstruction contribution  >= 0.10
proceed if either clears; halt only if both fail
```

This is an **effect-size discovery threshold, not a significance test**. The
pilot is sized for effect estimation rather than power: at roughly 200 paired
focal atoms a five-point binary contrast has an interval wide enough to be
interpretively ambiguous, whereas a ten-point effect is separable at that scale.
A significance criterion would also invite optional stopping across atom classes,
which a fixed effect size on a predeclared class does not.

Intervals are reported throughout and no p-value gates any decision. No post-hoc
threshold adjustment is permitted.

A low reconstruction rate in the randomised arm **alone** is evidence that the
manipulation worked, and is explicitly not grounds to halt.

## Exclusions

Every exclusion is decided **pre-treatment**. Filtering after observing
transmission would make the analysis set a function of the relay's decisions —
the exact selection the design exists to remove.

Reported rates: conflict groups, entangled surface forms, degenerate values,
human rejections, unverified atoms, invalid edits, coherence-audit failures, and
atoms with no matched-length eviction partner.
