# Reproduction and Verification Runbook

This directory contains executable entry points for verifying and reproducing the `handoff-fidelity` research package.

## Step 01: Verify Record Integrity

Validates that all protocol specifications, manifests, schemas, and blinded receipts match their cryptographic SHA-256 digests in `reproducibility/00_release/RECORD_MANIFEST.json`.

```bash
python reproducibility/14_replay/01_verify_record_integrity.py
```

## Step 02: Run Test Suite

Executes the full test matrix covering atomizer proposition extraction, counterfactual interventions, causal estimation, policy evaluation, and boundary conditions.

```bash
python reproducibility/14_replay/02_run_verification_suite.py
```
