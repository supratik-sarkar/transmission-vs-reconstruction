# PRE-REGISTRATION — Transmission vs Reconstruction Pilot (DRAFT v1.2)

> **UNFROZEN. NOT BINDING. NO STAGE-1 MODEL CALL MAY USE THIS FILE AS A FINAL PROTOCOL.**

## Binding prerequisites

Before freezing, replace every `UNFROZEN` field and hash the final artifact bundle non-circularly.

### Infrastructure

- Relay provider/model exact version: `UNFROZEN`
- Receiver provider/model exact version: `UNFROZEN`
- Operational decoder regime: `UNFROZEN pending calibration`
- Final source-frame identifier/hash: `UNFROZEN`
- Final source-pool identifier/hash: `UNFROZEN`
- Relay budget B/tokenizer: `UNFROZEN`

## Planned constants retained from the current design

- Stage 1: 100 new documents
- Stage 2: 300 new, disjoint confirmatory documents
- k = 3 focal atoms/document
- focal sampling: choose 3 populated strata uniformly WOR, then 1 atom/stratum
- pi_iz = (3/m_i)(1/n_is)
- m_prior = 25 auxiliary stochastic prior probes if retained after calibration
- eligible prior-gate classes: scope, numeric
- prior gate = 0.10
- reconstruction contribution gate = 0.10
- sham sampling target = 0.15
- document-cluster bootstrap target = 10,000 replicates
- master seed = 20260907

## Required pre-freeze validation

- source extraction calibration on disjoint calibration CIKs;
- human-verified atom inventory procedure frozen;
- matcher precision >=.95 and recall >=.95;
- editor invariance/coherence audit;
- operational decoder-repeatability audit;
- empirical no-evidence baselines;
- Experiment-B context tuple/skeleton validation;
- intervention-failure thresholds fixed;
- all prompts/specs/support/code hashed.

## Outcome-inspection rule

Calibration-only outputs may be inspected solely for preregistered instrument-validation criteria. No Stage-1/Stage-2 experimental outcome may be inspected before all Stage-1 documents are processed.

## Freeze architecture

1. create `ARTIFACT_MANIFEST.json` over frozen artifacts;
2. insert manifest hash into final preregistration;
3. hash final preregistration;
4. create external/private `FREEZE_RECORD.json` with prereg, manifest, source-pool hashes, Git commit, model versions, UTC timestamp;
5. verify via `handoff protocol verify`.
