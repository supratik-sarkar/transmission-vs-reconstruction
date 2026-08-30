# Protocol directory

This directory contains **public, version-controlled protocol artifacts**.

## Important status

The current contents are **DRAFT / UNFROZEN** until a binding preregistration and freeze record are produced. Do not infer that a file's presence means it was used in an experiment.

A real Stage-1 run must satisfy all of the following:

1. exact source frame and final source pool frozen;
2. exact relay/receiver model versions pinned;
3. calibration-only validation complete;
4. prompts/specs/code/support files frozen;
5. `ARTIFACT_MANIFEST.json` generated;
6. final preregistration references that manifest hash;
7. private `FREEZE_RECORD.json` generated and verified;
8. `handoff protocol verify` returns PASS.

The runtime CLI refuses real Stage-1 execution without the private freeze record.
