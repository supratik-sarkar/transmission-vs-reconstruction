from handoff_fidelity.gates import evaluate_stage1_gate


def test_either_gate_proceeds() -> None:
    assert evaluate_stage1_gate(
        reconstruction_contribution=0.11, prior_effects={"scope": 0.01}
    ).proceed
    assert evaluate_stage1_gate(
        reconstruction_contribution=0.01, prior_effects={"numeric": 0.11}
    ).proceed
    assert not evaluate_stage1_gate(
        reconstruction_contribution=0.01, prior_effects={"numeric": 0.09}
    ).proceed
