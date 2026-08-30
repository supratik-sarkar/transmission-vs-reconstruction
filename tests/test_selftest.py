from handoff_fidelity.selftest import run_design_selftests


def test_design_selftests() -> None:
    result = run_design_selftests()
    assert set(result.values()) == {"PASS"}
