# Deterministic policy tests. Run with: opa test policies/
package handoff.lifecycle_test

import data.handoff.lifecycle
import rego.v1

full_freeze := {
	"relay_model_pinned": true, "receiver_model_pinned": true,
	"causalrelay_artifact_frozen": true, "calibration_parameters_resolved": true,
	"focal_sampling_frozen": true, "renderer_frozen": true, "matcher_frozen": true,
	"sota_revisions_frozen": true, "analysis_revision_frozen": true,
	"bootstrap_frozen": true, "source_manifest_frozen": true,
	"test_manifest_frozen": true, "final_test_freeze_present": true,
}

ready_test_input := {
	"action": "run_stage2_test", "subject": "cli", "mode": "RESEARCH_MODE",
	"provider": "openai", "relay_model_pinned": true, "receiver_model_pinned": true,
	"calibration_parameters_resolved": true, "protocol_freeze_present": true,
	"final_test_freeze_present": true, "stage1_gate_passed": true,
	"freeze_fields": full_freeze,
}

# Final test is denied when nothing is frozen.
test_final_test_denied_without_freeze if {
	not lifecycle.allow with input as {
		"action": "run_stage2_test", "subject": "cli", "mode": "RESEARCH_MODE",
		"provider": "openai", "freeze_fields": {},
	}
}

# Final test is denied if a SINGLE freeze requirement is missing.
test_final_test_denied_on_one_missing_requirement if {
	not lifecycle.allow with input as object.union(
		ready_test_input,
		{"freeze_fields": object.union(full_freeze, {"renderer_frozen": false})},
	)
}

test_final_test_allowed_when_fully_frozen if {
	lifecycle.allow with input as ready_test_input
}

# Development denied without model pins.
test_development_denied_without_model_pins if {
	not lifecycle.allow with input as {
		"action": "run_stage2_dev", "subject": "cli", "mode": "RESEARCH_MODE",
		"provider": "openai", "protocol_freeze_present": true,
		"stage1_gate_passed": true, "calibration_parameters_resolved": true,
		"relay_model_pinned": false, "receiver_model_pinned": false,
		"freeze_fields": {},
	}
}

# The browser may never launch the final test.
test_browser_denied_final_test if {
	not lifecycle.allow with input as object.union(
		ready_test_input, {"subject": "browser"},
	)
}

test_browser_denied_stage1 if {
	not lifecycle.allow with input as {
		"action": "run_stage1", "subject": "browser", "mode": "RESEARCH_MODE",
		"provider": "openai", "protocol_freeze_present": true,
		"relay_model_pinned": true, "receiver_model_pinned": true,
		"freeze_fields": {},
	}
}

# A synthetic demo run is permitted from the browser, in demo mode only.
test_demo_synthetic_permitted if {
	lifecycle.allow with input as {
		"action": "run_demo_synthetic", "subject": "browser", "mode": "DEMO_MODE",
		"provider": "mock", "freeze_fields": {},
	}
}

test_demo_synthetic_denied_in_research_mode if {
	not lifecycle.allow with input as {
		"action": "run_demo_synthetic", "subject": "browser", "mode": "RESEARCH_MODE",
		"provider": "mock", "freeze_fields": {},
	}
}

# Guardrails on the scientific path are always denied.
test_guardrails_in_inference_denied if {
	not lifecycle.allow with input as {
		"action": "enable_guardrails_in_inference", "subject": "cli",
		"mode": "DEMO_MODE", "provider": "mock", "freeze_fields": {},
	}
}

# Unknown provider denied.
test_unknown_provider_denied if {
	not lifecycle.allow with input as {
		"action": "run_demo_synthetic", "subject": "browser", "mode": "DEMO_MODE",
		"provider": "some-unapproved-provider", "freeze_fields": {},
	}
}

# Frozen parameters are immutable.
test_mutate_frozen_parameter_denied if {
	not lifecycle.allow with input as {
		"action": "mutate_frozen_parameter", "subject": "cli", "mode": "DEMO_MODE",
		"provider": "mock", "freeze_fields": {},
	}
}
