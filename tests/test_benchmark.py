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
from handoff_fidelity.baselines.registry import (
    RESOLVED_AS_INAPPLICABLE,
    BaselineEntry,
    Registry,
)
from handoff_fidelity.benchmark.reproduction import ReproductionRun, TestInspectionError
from handoff_fidelity.benchmark.runner import (
    BenchmarkPlan,
    EndpointOnlyMisuse,
    MethodRun,
    assert_causal_allowed,
    run_document,
)
from handoff_fidelity.benchmark.superiority import (
    PairedComparison,
    evaluate,
)
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


def test_registry_has_three_benchmark_ready_primary_families_and_two_blocked():
    registry = Registry.load("configs/baselines.yaml")
    assert registry.eligible_primary() == ["dac", "llmlingua2", "longllmlingua"]
    assert registry.superiority_denominator() == 5
    ok, statement = registry.headline_eligible()
    assert ok is True
    assert "3 distinct families available" in statement


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
    assert verdict.denominator == len(PRIMARY_SOTA)
    assert verdict.permitted is False


def test_config_hash_is_order_independent():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_a_bare_not_required_sentinel_does_not_resolve_a_field():
    """`NOT_REQUIRED` is a resolution only when it comes with a reason.

    Without the paired reason it is indistinguishable from a placeholder typed
    to make a gate go green, so the field stays unresolved.
    """
    bare = BaselineEntry(name="x", role="PRIMARY_CAUSAL", commit=RESOLVED_AS_INAPPLICABLE)
    assert "commit" in bare.unresolved()

    justified = BaselineEntry(
        name="x",
        role="PRIMARY_CAUSAL",
        commit=RESOLVED_AS_INAPPLICABLE,
        commit_not_required_reason="inference code ships inside the checkpoint repository",
    )
    assert "commit" not in justified.unresolved()


def test_the_amended_primary_set_spans_five_distinct_families():
    """After P-6, P-7, and P-9 the five primaries span five distinct families.
    Provence (cross_encoder_sentence), CPC (decoder_lora_sentence),
    LLMLingua-2 (token_classification_xlmr), DAC (decoder_attention_entropy_token),
    and LongLLMLingua (causal_lm_perplexity_conditioned_compression).
    """
    registry = Registry.load("configs/baselines.yaml")
    primaries = sorted(n for n, e in registry.entries.items() if e.role == "PRIMARY_CAUSAL")
    assert primaries == ["cpc", "dac", "llmlingua2", "longllmlingua", "provence"]
    assert len(registry.families_of(primaries)) == 5
    # The original collision is still recorded, so the reason for the amendment
    # does not quietly disappear from the config.
    assert registry.method_families["token_classification_xlmr"] == [
        "llmlingua2",
        "adaptive_queryselect",
    ]
    assert registry.method_families["causal_lm_perplexity_conditioned_compression"] == [
        "longllmlingua"
    ]


def test_adaptive_queryselect_is_retired_pre_outcome_not_deleted():
    registry = Registry.load("configs/baselines.yaml")
    entry = registry.entries["adaptive_queryselect"]
    assert entry.role == "RETIRED_PRE_OUTCOME"
    assert entry.replaced_by == "dac"
    assert entry.counts_toward_superiority is False
    ok, reason = entry.benchmark_eligible()
    assert ok is False
    assert "retired pre-outcome" in reason
    # The amendment history must survive in machine-readable form.
    p6 = next(a for a in registry.amendments if a["id"] == "P-6")
    assert p6["benchmark_outcomes_observed_before_amendment"] == 0
    assert p6["removed"] == "adaptive_queryselect"
    assert p6["added"] == "dac"
    assert p6["removal_reason"] == "missing_executable_artefact"


def test_selective_context_is_contingency_only():
    registry = Registry.load("configs/baselines.yaml")
    entry = registry.entries["selective_context"]
    assert entry.role == "CONTINGENCY_CAUSAL"
    assert entry.counts_toward_superiority is False
    # It is pinnable -- that is not the same as being in the primary set.
    assert entry.commit == "b8ad75c18f696571c1543817004914f06ba093f2"  # pragma: allowlist secret
    assert entry.release_tag == "v0.1.0rc1"
    ok, reason = entry.benchmark_eligible()
    assert ok is False
    assert "contingency" in reason
    assert "irreproducible_native_implementation" in entry.promotion_permitted_reasons
    # A contingency comparator is not counted in the primary denominator.
    assert registry.superiority_denominator() == 5


def test_native_example_pass_cannot_satisfy_benchmark_ready_gate():
    """NATIVE_EXAMPLE_PASS != BENCHMARK_READY. The status alone must fail benchmark_eligible."""
    entry = BaselineEntry(
        name="test_method",
        role="PRIMARY_CAUSAL",
        status="NATIVE_EXAMPLE_PASS",
        paper_citation_key="key",
        official_repository="repo",
        commit="commit",
        release_tag="tag",
        checkpoint_revision="rev",
        licence="MIT",
        python_requirement="3.11",
        install_command="pip install x",
        native_benchmark="bench",
        native_expected_metric=50.0,
        native_reproduced_metric=50.0,
        reproduction_deviation=0.0,
        reproduction_tolerance=2.0,
    )
    ok, reason = entry.benchmark_eligible()
    assert ok is False
    assert "adapter status is NATIVE_EXAMPLE_PASS" in reason


def test_blocked_provence_and_cpc_cannot_silently_become_eligible():
    """Blocked comparators must remain ineligible unless formally resolved."""
    registry = Registry.load("configs/baselines.yaml")
    prov_ok, prov_reason = registry.entries["provence"].benchmark_eligible()
    assert prov_ok is False
    assert registry.entries["provence"].status == "LICENCE_CLARIFICATION_REQUIRED"
    assert "unresolved" in prov_reason or "LICENCE_CLARIFICATION_REQUIRED" in prov_reason

    cpc_ok, cpc_reason = registry.entries["cpc"].benchmark_eligible()
    assert cpc_ok is False
    assert registry.entries["cpc"].status == "NOT_READY"
    assert "unresolved" in cpc_reason or "NOT_READY" in cpc_reason


def test_calibration_documents_equals_50():
    """Amendment P-8 sets calibration documents to 50, frozen."""
    from pathlib import Path

    import yaml

    doc = yaml.safe_load(Path("configs/preregistration_v1_2.yaml").read_text(encoding="utf-8"))
    assert doc["stages"]["calibration"]["documents"] == 50
    assert doc["stages"]["calibration"]["status"] == "frozen"


def test_amendments_p8_and_p9_zero_outcome_timing():
    """P-8 and P-9 were enacted with zero observed benchmark outcomes."""
    from pathlib import Path

    import yaml

    doc = yaml.safe_load(Path("configs/preregistration_v1_2.yaml").read_text(encoding="utf-8"))
    p8 = next(a for a in doc["amendments"] if a["id"] == "P-8")
    assert p8["benchmark_outcomes_observed_before_amendment"] == 0
    assert p8["kind"] == "PRE_OUTCOME_PROTOCOL_COMPLETION"

    p9 = next(a for a in doc["amendments"] if a["id"] == "P-9")
    assert p9["benchmark_outcomes_observed_before_amendment"] == 0
    assert p9["kind"] == "comparator_contingency_activation"


def test_third_family_gate_requires_distinct_method_families():
    """Superiority headline requires >= 3 distinct declared method families."""
    registry = Registry.load("configs/baselines.yaml")
    ready_primaries = registry.eligible_primary()
    assert len(ready_primaries) >= 3
    distinct_families = registry.families_of(ready_primaries)
    assert len(distinct_families) >= 3
    assert distinct_families == {
        "token_classification_xlmr",
        "decoder_attention_entropy_token",
        "causal_lm_perplexity_conditioned_compression",
    }
    ok, _ = registry.headline_eligible()
    assert ok is True


# --------------------------------------------------------------------------
# P-7: the family-aware superiority gate
# --------------------------------------------------------------------------

_FAMILIES = {
    "provence": "cross_encoder_sentence",
    "cpc": "decoder_lora_sentence",
    "llmlingua2": "token_classification_xlmr",
    "dac": "decoder_attention_entropy_token",
    "longllmlingua": "causal_lm_perplexity_conditioned_compression",
}


def _win(name):
    return PairedComparison(name, (0.05, 0.01, 0.09), (0.04, 0.01, 0.07))


def _loss(name):
    return PairedComparison(name, (0.01, -0.02, 0.04), (0.01, -0.02, 0.04))


def test_family_gate_rejects_a_field_narrower_than_three_families():
    """Fewer than three distinct ready families means no headline at all.

    This fires before any comparison is examined: a narrow field is a design
    limitation, not a lost contest.
    """
    verdict = evaluate(
        [_win("llmlingua2"), _win("dac")],
        eligible_primary=["llmlingua2", "dac"],
        registered_primary=["provence", "cpc", "llmlingua2", "dac"],
        family_map=_FAMILIES,
    )
    assert verdict.headline_eligible is False
    assert verdict.permitted is False
    assert "NO SOTA-SUPERIORITY HEADLINE" in verdict.statement
    assert len(verdict.eligible_families) == 2


def test_family_gate_requires_beating_all_three_when_exactly_three_families():
    eligible = ["provence", "cpc", "llmlingua2"]
    two_of_three = evaluate(
        [_win("provence"), _win("cpc"), _loss("llmlingua2")],
        eligible_primary=eligible,
        registered_primary=["provence", "cpc", "llmlingua2", "dac"],
        family_map=_FAMILIES,
    )
    assert two_of_three.headline_eligible is True
    assert two_of_three.permitted is False
    assert "all eligible comparators must be beaten" in two_of_three.statement

    all_three = evaluate(
        [_win("provence"), _win("cpc"), _win("llmlingua2")],
        eligible_primary=eligible,
        registered_primary=["provence", "cpc", "llmlingua2", "dac"],
        family_map=_FAMILIES,
    )
    assert all_three.permitted is True
    assert len(all_three.winning_families) == 3


def test_family_gate_permits_three_wins_spanning_three_families_out_of_four():
    verdict = evaluate(
        [_win("provence"), _win("cpc"), _win("dac"), _loss("llmlingua2")],
        eligible_primary=["provence", "cpc", "llmlingua2", "dac"],
        family_map=_FAMILIES,
    )
    assert verdict.permitted is True
    assert verdict.winning_families == (
        "cross_encoder_sentence",
        "decoder_attention_entropy_token",
        "decoder_lora_sentence",
    )


def test_three_wins_inside_two_families_do_not_permit_a_headline():
    """The exact failure P-7 exists to prevent.

    Three wins, but two of them are the same method with a different classifier
    head. Under the old count-only rule this passed.
    """
    families = dict(_FAMILIES)
    families["adaptive_queryselect"] = "token_classification_xlmr"
    verdict = evaluate(
        [_win("llmlingua2"), _win("adaptive_queryselect"), _win("provence"), _loss("cpc")],
        eligible_primary=["llmlingua2", "adaptive_queryselect", "provence", "cpc"],
        family_map=families,
    )
    assert len(verdict.wins) == 3
    assert verdict.permitted is False
    assert "distinct method families" in verdict.statement
