# Reproducibility Record

This directory contains the protocol definitions, frozen contracts, sampling manifests, execution receipts, and blinded audit materials for the `handoff-fidelity` (`transmission-vs-reconstruction`) research package.

## Directory Structure

```text
reproducibility/
├── 00_release/           # Release manifests, cryptographic seals, and artifact ledger
├── 01_protocol/          # Preregistration, budget calibration, and estimand definitions
├── 02_configs/           # Dependency schemas and execution parameterizations
├── 03_inputs/            # Document-level focal candidate and selection manifests
├── 04_interventions/     # Intervention validity specifications and records
├── 05_execution/         # Cryptographic receipts and aggregate sample digests
├── 06_human_audit/       # Blinded audit review sheets and reserve test manifests
├── 07_scoring/           # Causal scoring schemas and state accounting
├── 08_statistics/        # Statistical estimation protocols and variance estimation
├── 09_results/           # Canonical evaluation series data
├── 10_artifacts/         # Methodological diagrams and compiled figures
├── 11_environment/       # Pinned dependencies and environment lockfiles
├── 12_code_provenance/   # Component hash manifests
├── 13_change_control/    # Versioning and specification notes
├── 14_replay/            # Verification and evaluation runners
└── tools/                # Record integrity and sealing utilities
```

## Versioning Architecture: Public Snapshot `v1-1` vs Scientific Contract `v3.1`

- **Public Repository Snapshot**: `v1-1` (the public research code and documentation release).
- **Scientific Contract Identifier**: `v3.1` (the underlying preregistered scientific design, sampling frame, and contract specification).
- **Provenance Integrity**: Certified protocol contracts and methodological artifacts (e.g. `*_v3`) carry their authoritative `v3.1` identifiers to preserve exact cryptographic provenance and hash continuity with the preregistered experimental protocol. They are not artificially renamed.

## Record Verification

To verify the integrity and cryptographic hashes of the reproducibility record:

```bash
python reproducibility/tools/seal_record.py --verify
```
