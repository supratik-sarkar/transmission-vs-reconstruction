"""Canonicalisation and token-boundary presence detection."""

from __future__ import annotations

from handoff_fidelity.matcher.canonical import (
    canonical_numeric,
    canonical_period,
    canonicalize,
)
from handoff_fidelity.matcher.match import find_spans, is_transmitted, recovered
from handoff_fidelity.matcher.validation import score, wilson_interval


def test_percentage_variants_canonicalise_identically():
    for variant in ("6.2%", "6.20 %", "6.2 percent", "6.2pct"):
        assert canonical_numeric(variant) == "6.2%"


def test_currency_magnitudes_are_resolved():
    assert canonical_numeric("$1.5 billion") == canonical_numeric("USD 1,500,000,000")


def test_decimal_equivalence_is_exact_not_float():
    assert canonical_numeric("0.1%") == canonical_numeric("0.10 %")
    assert canonical_numeric("1.10") == canonical_numeric("1.1")


def test_period_variants_canonicalise_identically():
    for variant in ("FY2023", "fiscal 2023", "fiscal year 2023", "2023"):
        assert canonical_period(variant) == "FY2023"
    for variant in ("Q1 2023", "Q1 FY2023", "the first quarter of 2023"):
        assert canonical_period(variant) == "FY2023Q1"


def test_substring_matching_is_not_used_for_entities():
    """A naive substring test reports 'Alder' as present inside
    'Alder Ridge Holdings'-adjacent text. That inflates T, the denominator of
    half the analysis."""
    assert (
        is_transmitted("Alderman Group reported", canonical_value="alder", role="entity") is False
    )
    assert is_transmitted("Alder reported", canonical_value="alder", role="entity") is True


def test_substring_matching_is_not_used_for_periods():
    assert is_transmitted("results for FY20231", canonical_value="FY2023", role="period") is False
    assert is_transmitted("results for FY2023", canonical_value="FY2023", role="period") is True


def test_numeric_presence_is_not_a_prefix_match():
    assert is_transmitted("margin rose 62.5%", canonical_value="6.2%", role="numeric") is False
    assert is_transmitted("margin rose 6.2%", canonical_value="6.2%", role="numeric") is True


def test_find_spans_locates_every_occurrence():
    msg = "margin rose 6.2% and later 6.20 % again"
    spans = find_spans(msg, canonical_value="6.2%", role="numeric")
    assert len(spans) == 2


def test_spans_do_not_overlap():
    msg = "North America and North America again"
    spans = find_spans(msg, canonical_value="north america", role="scope")
    assert len(spans) == 2
    assert spans[0].end <= spans[1].start


def test_recovered_accepts_a_bare_slot_answer():
    assert recovered("6.2%", canonical_value="6.2%", role="numeric") is True
    assert recovered("FY2023", canonical_value="FY2023", role="period") is True
    assert recovered("7.9%", canonical_value="6.2%", role="numeric") is False


def test_canonicalize_dispatches_by_role():
    assert canonicalize("FY2023", "period") == "FY2023"
    assert canonicalize("6.2 %", "numeric") == "6.2%"
    assert canonicalize("North America", "scope") == "north america"


def test_validation_requires_both_precision_and_recall():
    """A matcher that almost never fires has perfect precision and useless
    recall. Precision alone is not a gate."""
    predicted = [True] * 10 + [False] * 190
    truth = [True] * 100 + [False] * 100
    outcome = score(predicted, truth)
    assert outcome.precision == 1.0
    assert outcome.recall < 0.2
    assert outcome.passed is False


def test_validation_requires_the_stratified_sample_size():
    predicted = [True] * 50 + [False] * 50
    truth = [True] * 50 + [False] * 50
    outcome = score(predicted, truth)
    assert outcome.precision == 1.0 and outcome.recall == 1.0
    assert outcome.passed is False, "a 100-item sample must not pass the 200-item gate"


def test_validation_passes_a_good_matcher():
    predicted = [True] * 98 + [False] * 2 + [False] * 99 + [True]
    truth = [True] * 100 + [False] * 100
    outcome = score(predicted, truth)
    assert outcome.passed is True


def test_wilson_interval_brackets_the_point():
    lo, hi = wilson_interval(95, 100)
    assert lo < 0.95 < hi
