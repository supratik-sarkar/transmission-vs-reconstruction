"""Adapter contract, budget enforcement, focal secrecy, endpoint-only split."""

from __future__ import annotations

from dataclasses import dataclass

from handoff_fidelity.baselines.base import (
    AdapterNotReady,
    AdapterStatus,
    BaseCompressor,
    BenchmarkRole,
    BudgetViolation,
    config_hash,
)
from handoff_fidelity.baselines.controls import FullContext, HeadTruncation, UniformAtoms
from handoff_fidelity.baselines.external import BUILDERS, PRIMARY_SOTA
from handoff_fidelity.baselines.registry import BaselineEntry, Registry
from handoff_fidelity.benchmark.reproduction import ReproductionRun, TestInspectionError
from handoff_fidelity.benchmark.runner import (
    BenchmarkPlan,
    EndpointOnlyMisuse,
    MethodRun,
    assert_causal_allowed,
    run_document,
)
from handoff_fidelity.benchmark.superiority import PairedComparison, evaluate
from handoff_fidelity.models import AtomRole
from handoff_fidelity.relay.task import GLOBAL_DOWNSTREAM_TASK, FocalLeakError, assert_no_focal_leak

from ._support import FakeTokenizer, atom, raises


@dataclass(slots=True)
class Overrunner(BaseCompressor):
    name: str = "overrunner"
    revision: str = "test"
    status: AdapterStatus = AdapterStatus.READY
    role: BenchmarkRole = BenchmarkRole.CONTROL

    def _compress(self, source_text, downstream_task, token_budget, config):
        return source_text, ()


def test_adapter_returns_the_uniform_result_shape():
    tok = FakeTokenizer()
    result = HeadTruncation(tokenizer=tok).compress("a b c d e f", GLOBAL_DOWNSTREAM_TASK, 3)
    for field in (
        "text",
        "input_tokens",
        "output_tokens",
        "latency_s",
        "method",
        "revision",
        "configuration_hash",
        "warnings",
        "budget",
    ):
        assert hasattr(result, field)
    assert result.output_tokens <= 3
    assert result.within_budget


def test_budget_violation_is_fatal_not_a_warning():
    """No method may get a larger effective context than another."""
    tok = FakeTokenizer()
    with raises(BudgetViolation):
        Overrunner(tokenizer=tok).compress("a b c d e f g h", GLOBAL_DOWNSTREAM_TASK, 3)


def test_full_context_is_exempt_because_it_is_a_reference_bound():
    tok = FakeTokenizer()
    result = FullContext(tokenizer=tok).compress("a b c d e f g h", GLOBAL_DOWNSTREAM_TASK, 3)
    assert result.output_tokens > 3
    assert any("not budget matched" in w for w in result.warnings)


def test_uniform_atoms_respects_the_budget_and_uses_the_shared_renderer():
    tok = FakeTokenizer()
    atoms = [atom(AtomRole.SCOPE, f"scope-{i}", start=i * 10) for i in range(20)]
    result = UniformAtoms(tokenizer=tok, atoms=atoms, seed=3).compress(
        "irrelevant", GLOBAL_DOWNSTREAM_TASK, 12
    )
    assert result.output_tokens <= 12
    assert result.text.startswith("- ")


def test_focal_values_never_reach_a_compressor():
    """Otherwise focal sampling becomes supervision for query-aware methods."""
    with raises(FocalLeakError):
        assert_no_focal_leak("preserve the 6.2% figure", ["6.2%"])
    assert_no_focal_leak(GLOBAL_DOWNSTREAM_TASK, ["6.2%", "FY2019"])


def test_focal_leak_is_checked_on_the_configuration_too():
    tok = FakeTokenizer()
    method = HeadTruncation(tokenizer=tok)
    with raises(FocalLeakError):
        method.compress(
            "a b c", GLOBAL_DOWNSTREAM_TASK, 3, {"keep": "FY2019"}, focal_values=["FY2019"]
        )


def test_not_ready_adapters_raise_rather_than_approximate():
    """A speculative reimplementation labelled with a published method's name
    would misrepresent the benchmark."""
    for name in PRIMARY_SOTA:
        adapter = BUILDERS[name]()
        assert adapter.status is AdapterStatus.NOT_READY
        with raises(AdapterNotReady):
            adapter.compress("text", GLOBAL_DOWNSTREAM_TASK, 100)


def test_endpoint_only_methods_cannot_populate_causal_metrics():
    run = MethodRun("parallelcomp", BenchmarkRole.ENDPOINT_ONLY, None, False)
    with raises(EndpointOnlyMisuse):
        assert_causal_allowed(run)


def test_plan_skips_not_ready_methods_and_records_them():
    tok = FakeTokenizer()
    plan = BenchmarkPlan(
        budget=5,
        methods={
            "head_truncation": HeadTruncation(tokenizer=tok),
            "provence": BUILDERS["provence"](),
        },
    )
    runs = run_document(plan, source_text="a b c d e f g")
    assert "head_truncation" in runs
    assert "provence" not in runs
    assert any("NOT_READY" in w for w in plan.warnings)


def test_registry_reports_unresolved_fields_rather_than_guessing():
    entry = BaselineEntry(name="x", role="PRIMARY_CAUSAL")
    ok, reason = entry.benchmark_eligible()
    assert ok is False
    assert "unresolved registry fields" in reason
    assert "commit" in entry.unresolved()


def test_registry_blocks_a_method_outside_reproduction_tolerance():
    entry = BaselineEntry(
        name="x",
        role="PRIMARY_CAUSAL",
        status="READY",
        paper_citation_key="k",
        official_repository="r",
        commit="c",
        release_tag="t",
        checkpoint_revision="rev",
        licence="MIT",
        python_requirement="3.12",
        install_command="pip install x",
        native_benchmark="b",
        native_expected_metric=50.0,
        native_reproduced_metric=40.0,
        reproduction_tolerance=2.0,
        reproduction_deviation=-10.0,
    )
    ok, reason = entry.benchmark_eligible()
    assert ok is False
    assert "UNREPRODUCED" in reason


def test_shipped_registry_has_every_external_method_unresolved():
    registry = Registry.load("configs/baselines.yaml")
    assert registry.eligible_primary() == []
    assert registry.superiority_denominator() == 4


def test_reproduction_may_not_be_pointed_at_the_sealed_test_split():
    with raises(TestInspectionError):
        ReproductionRun(method="x", split="stage2_test")
    ReproductionRun(method="x", split="stage2_dev")


def test_reproduction_verdict_requires_every_step():
    run = ReproductionRun(
        method="x",
        split="calibration",
        steps=dict.fromkeys(
            (
                "environment_installs",
                "checkpoint_loads",
                "native_example_runs",
                "output_is_textual",
                "budget_adapter_works",
            ),
            True,
        ),
        observed_metric=49.0,
        expected_metric=50.0,
        tolerance=2.0,
    )
    ok, failures = run.verdict()
    assert ok is True and failures == []
    run.steps["output_is_textual"] = False
    ok, failures = run.verdict()
    assert ok is False and "output_is_textual" in failures


def _cmp(name, a_lo, c_lo):
    return PairedComparison(name, (0.05, a_lo, 0.10), (0.05, c_lo, 0.10))


def test_superiority_requires_three_wins_on_both_bounds():
    comparisons = [_cmp(n, 0.01, 0.01) for n in PRIMARY_SOTA[:3]] + [
        _cmp(PRIMARY_SOTA[3], -0.01, 0.01)
    ]
    verdict = evaluate(comparisons, eligible_primary=PRIMARY_SOTA, registered_primary=PRIMARY_SOTA)
    assert verdict.permitted is True
    assert len(verdict.wins) == 3


def test_two_wins_do_not_permit_a_comparative_claim():
    comparisons = [_cmp(n, 0.01, 0.01) for n in PRIMARY_SOTA[:2]] + [
        _cmp(n, 0.01, -0.01) for n in PRIMARY_SOTA[2:]
    ]
    verdict = evaluate(comparisons, eligible_primary=PRIMARY_SOTA, registered_primary=PRIMARY_SOTA)
    assert verdict.permitted is False
    assert "NOT permitted" in verdict.statement


def test_one_positive_bound_is_not_a_win():
    """Both delta_A and delta_C_comm must clear zero."""
    comparisons = [_cmp(n, 0.01, -0.01) for n in PRIMARY_SOTA]
    verdict = evaluate(comparisons, eligible_primary=PRIMARY_SOTA, registered_primary=PRIMARY_SOTA)
    assert verdict.wins == ()


def test_adding_a_comparator_after_the_fact_is_an_error():
    comparisons = [_cmp(n, 0.9, 0.9) for n in PRIMARY_SOTA] + [_cmp("easy_method", 0.9, 0.9)]
    with raises(ValueError):
        evaluate(comparisons, eligible_primary=PRIMARY_SOTA, registered_primary=PRIMARY_SOTA)


def test_denominator_is_the_registered_suite_not_the_eligible_subset():
    """Dropping unreproduced comparators from the denominator would let a
    failure to reproduce manufacture a win."""
    comparisons = [_cmp(n, 0.9, 0.9) for n in PRIMARY_SOTA[:2]]
    verdict = evaluate(
        comparisons, eligible_primary=PRIMARY_SOTA[:2], registered_primary=PRIMARY_SOTA
    )
    assert verdict.denominator == 4
    assert verdict.permitted is False


def test_config_hash_is_order_independent():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})
