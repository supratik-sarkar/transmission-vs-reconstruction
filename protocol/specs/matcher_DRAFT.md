# Canonical matcher — DRAFT / UNFROZEN

Tier-1 primary outcomes use deterministic canonical matching rather than an LLM judge.

## Candidate normalization

- Unicode NFKC;
- lowercase for text roles;
- trim/collapse whitespace;
- role-specific period normalization;
- numeric normalization preserving sign and two decimal places;
- source/response units must be compatible.

## Validation

Before Stage 1, validate on a disjoint human-labelled calibration set with BOTH:

- precision >= 0.95;
- recall >= 0.95.

The exact calibration sampling and adjudication procedure must be frozen in the preregistration.
