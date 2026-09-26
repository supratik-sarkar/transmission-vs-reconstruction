# Human Audit Protocol (S9)

This directory defines the blinded human audit protocol for validating the automated matcher and evaluation metrics.

## Status: PENDING_REAL_HUMAN_S9

The empirical human certification protocol (S9) is currently pending completion by independent annotators under double-blind conditions.

### Protocol Summary
- **Design**: Blinded dual-annotator review across a stratified reserve panel of 600 audit cases.
- **Annotators**: Two independent human annotators evaluate each candidate transmission note and corresponding source evidence without access to receiver identities or experimental conditions.
- **Adjudication**: Any inter-annotator disagreements are submitted to blinded consensus adjudication to produce certified reference labels.
- **Gate Criteria**: Automated matcher agreement must satisfy $\kappa \ge 0.80$ against the final consensus labels before downstream certification is unlocked.

### Asset Segregation Policy
In accordance with double-blind audit hygiene:
- Live audit execution inputs—including active blinded review sheets (`BLINDED_REVIEW_SHEET_ANNOTATOR_A.csv`, `BLINDED_REVIEW_SHEET_ANNOTATOR_B.csv`), uncertified reserve provider responses (`S9_RESERVE_RESPONSES.jsonl`), and reserve manifests—are maintained in the private development workspace during active review.
- Upon completion of the dual-annotator review and adjudication protocol, the final certified consensus labels and verification receipts will be published under `reproducibility/06_human_audit/certified_labels/` for public reproducibility.
