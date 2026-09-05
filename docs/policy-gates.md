# Policy gates

Open Policy Agent governs **lifecycle** questions only:

* may this stage start?
* are the models pinned?
* is the provider approved?
* are calibration-selected values resolved?
* is the final-test freeze complete?
* may this subject perform this action?

It must never answer a **scientific** question. It cannot decide which result is
favourable, whether an observation may be discarded, or whether a method wins.
Encoding those here would let an operator change a result by editing a rule.

## Two engines, one answer

`policies/rego/lifecycle.rego` is mirrored by `policy/decisions.py`. A shared
test-case table keeps them in lockstep, and when they disagree the engine
**denies and reports the disagreement** rather than taking either answer.

The mirror exists so the CLI's fail-closed guards never depend on an external
binary being installed. If OPA is absent, the mirror decides — and it is
fail-closed.

## Final-test denial

The sealed test is denied unless every one of these is true:

```
relay_model_pinned              analysis_revision_frozen
receiver_model_pinned           bootstrap_frozen
causalrelay_artifact_frozen     source_manifest_frozen
calibration_parameters_resolved test_manifest_frozen
focal_sampling_frozen           final_test_freeze_present
renderer_frozen
matcher_frozen
sota_revisions_frozen
```

A test asserts that **each requirement alone** produces a denial, so none is
decorative.

## The browser

The browser may perform exactly one action: launch a synthetic demo run, in demo
mode. Every real stage is denied to it, including the final test, in every mode.
There is deliberately no convenient button that could bypass this — the API
exposes no endpoint for it at all.
