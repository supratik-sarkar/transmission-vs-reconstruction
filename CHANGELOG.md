# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to semantic versioning.

## [0.2.0] — unreleased

### Added
- Relay-visible source frame with hashing, and a mechanical check that the atom
  inventory lies inside it.
- Rule-based Tier-1 atomizer with human-verification tooling, pre-treatment
  eligibility filtering and inter-rater agreement.
- Token-boundary canonical matcher with blinded stratified validation on both
  precision and recall.
- Availability editor with non-focal invariance checks, entangled-clause
  rejection and per-mechanism sham edits.
- Matched-skeleton construction, prior probe with reliability-aware
  stratification, and budget-neutral swap planning.
- Design-based estimation: Horvitz–Thompson, Hájek, two-phase weighting, the
  decomposition, selection-bias diagnostic and sham partial identification.
- Document-clustered bootstrap with paired method comparisons.
- `CausalRelay`: frozen pre-treatment features, grouped-by-document
  cross-validation, deterministic renderer shared with the uniform control, and
  deterministic allocation.
- Comparator adapter API with hard budget enforcement and focal secrecy; an
  immutable registry; and a reproduction gate.
- Stage specifications with fail-closed execution guards.
- Provenance: artifact manifests, two freeze records and a results manifest.
- Code-generated table fragments, figure scripts and a manuscript readiness
  guard that distinguishes conceptual from experimental figures.
- Privacy scan, public/private boundary guard and a deterministic self-test
  suite.

### Changed
- Focal sampling now draws `k` strata uniformly without replacement from **all**
  populated strata. The previous "most populated strata" rule assigned zero
  inclusion probability off-support, which leaves the Hájek estimator undefined
  on part of the target population rather than merely violating an assumption.
- Presence detection is token-boundary aware. Substring matching reported an
  entity as present inside a longer name and a period inside a longer period,
  inflating the measured transmission rate.
- The scientific core no longer depends on pydantic, pandas or a CLI framework;
  it uses the standard library and NumPy so invariants are checkable in a minimal
  environment.
- Chance references use `K_eff`, since the natural value is excluded from its own
  redraw support.

### Removed
- Flat modules superseded by the package layout.
- Documentation containing machine-specific paths and submission status.

## [0.1.0]

Initial repository skeleton.
