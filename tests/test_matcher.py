from handoff_fidelity.matcher import canonical_numeric, canonical_period, is_transmitted


def test_numeric_equivalence() -> None:
    assert canonical_numeric("6.2%") == "6.20"
    assert is_transmitted("Margin improved by 6.20 percent", canonical_value="6.20", role="numeric")


def test_period() -> None:
    assert canonical_period("FY 2023 Q4") == "FY2023Q4"
