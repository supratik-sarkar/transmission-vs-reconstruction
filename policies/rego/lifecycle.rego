# Lifecycle policy for the handoff-fidelity research programme.
#
# SCOPE: this policy answers LIFECYCLE questions only -- may this stage start,
# is the provider approved, is the freeze complete, may this subject act.
#
# It must never answer a SCIENTIFIC question. It cannot decide which result is
# favourable, whether an observation may be discarded, or whether a method wins.
# Those are not policy decisions and encoding them here would let an operator
# change a result by editing a rule.
#
# The Python mirror in src/handoff_fidelity/policy/decisions.py implements the
# same rules and is authoritative when OPA is unavailable. A shared test-case
# table keeps them in lockstep.

package handoff.lifecycle

import rego.v1

default allow := false

approved_providers := {"openai", "deepseek", "anthropic", "gemini", "mock"}

real_stages := {
	"run_stage1", "run_stage2_dev", "run_stage2_test",
	"run_experiment_c", "run_multihop",
}

post_gate_stages := {
	"run_stage2_dev", "run_stage2_test", "run_experiment_c", "run_multihop",
}

calibration_dependent := {"run_stage2_dev", "run_stage2_test"}

final_test_freeze_requirements := [
	"relay_model_pinned", "receiver_model_pinned", "causalrelay_artifact_frozen",
	"calibration_parameters_resolved", "focal_sampling_frozen", "renderer_frozen",
	"matcher_frozen", "sota_revisions_frozen", "analysis_revision_frozen",
	"bootstrap_frozen", "source_manifest_frozen", "test_manifest_frozen",
	"final_test_freeze_present",
]

# The browser may do exactly one thing: launch a synthetic demo run.
browser_allowed_actions := {"run_demo_synthetic"}

allow if count(deny) == 0

decision := {"allow": allow, "reasons": reasons}

reasons := deny if count(deny) > 0

reasons := ["allowed"] if count(deny) == 0

deny contains msg if {
	not approved_providers[input.provider]
	msg := sprintf("provider %q is not on the approved list", [input.provider])
}

deny contains msg if {
	input.subject == "browser"
	not browser_allowed_actions[input.action]
	msg := sprintf(
		"subject 'browser' may not perform %q; the browser is read-only for research actions",
		[input.action],
	)
}

deny contains msg if {
	input.action == "mutate_frozen_parameter"
	msg := "frozen parameters are immutable through any interface"
}

deny contains msg if {
	input.action == "enable_guardrails_in_inference"
	msg := "guardrails may never be attached to the scientific inference path"
}

deny contains msg if {
	input.action == "run_demo_synthetic"
	input.mode != "DEMO_MODE"
	msg := "synthetic demo runs require DEMO_MODE"
}

deny contains msg if {
	real_stages[input.action]
	not input.protocol_freeze_present
	msg := "protocol freeze record is absent"
}

deny contains msg if {
	real_stages[input.action]
	not input.relay_model_pinned
	msg := "relay_model is not pinned"
}

deny contains msg if {
	real_stages[input.action]
	not input.receiver_model_pinned
	msg := "receiver_model is not pinned"
}

deny contains msg if {
	post_gate_stages[input.action]
	not input.stage1_gate_passed
	msg := "the Stage-1 discovery gate has not passed"
}

deny contains msg if {
	calibration_dependent[input.action]
	not input.calibration_parameters_resolved
	msg := "calibration-selected parameters are unresolved"
}

deny contains msg if {
	input.action == "run_stage2_test"
	some requirement in final_test_freeze_requirements
	not input.freeze_fields[requirement]
	msg := sprintf("final-test freeze requirement unmet: %s", [requirement])
}
