"""Document-clustered bootstrap and paired comparisons."""

from __future__ import annotations

from handoff_fidelity.inference.bootstrap import (
    SMOKE_REPLICATES,
    cluster_bootstrap,
    paired_cluster_bootstrap,
    wilson_interval,
)

from ._support import raises, record


def _mean_delta(items):
    return sum(r.delta_avail for r in items) / len(items)


def _items(doc_values):
    return [
        record(doc=doc, aid=f"{doc}:{i}", t=1, r_minus=0.0, d_plus=v)
        for doc, values in doc_values.items()
        for i, v in enumerate(values)
    ]


def test_bootstrap_resamples_documents_not_atoms():
    """Atoms within a document share one relay realisation; resampling atoms
    would understate every interval."""
    items = _items({f"d{i}": [0.2, 0.8] for i in range(20)})
    interval = cluster_bootstrap(
        items,
        document_key=lambda r: r.document_id,
        statistic=_mean_delta,
        replicates=SMOKE_REPLICATES,
        seed=1,
    )
    assert interval.n_documents == 20
    assert interval.lower <= interval.point <= interval.upper


def test_bootstrap_is_reproducible_from_its_seed():
    items = _items({f"d{i}": [0.1 * i] for i in range(15)})
    kwargs = {
        "document_key": lambda r: r.document_id,
        "statistic": _mean_delta,
        "replicates": SMOKE_REPLICATES,
        "seed": 42,
    }
    assert (
        cluster_bootstrap(items, **kwargs).as_tuple()
        == cluster_bootstrap(items, **kwargs).as_tuple()
    )


def test_paired_bootstrap_requires_a_common_document_set():
    """Comparing methods on different documents would confound the method
    contrast with the document draw."""
    a = _items({"d1": [0.5], "d2": [0.5]})
    b = _items({"d1": [0.2]})
    with raises(ValueError):
        paired_cluster_bootstrap(
            a,
            b,
            document_key=lambda r: r.document_id,
            statistic=_mean_delta,
            replicates=10,
            seed=0,
        )


def test_paired_bootstrap_recovers_a_constant_offset():
    a = _items({f"d{i}": [0.6] for i in range(25)})
    b = _items({f"d{i}": [0.4] for i in range(25)})
    interval = paired_cluster_bootstrap(
        a,
        b,
        document_key=lambda r: r.document_id,
        statistic=_mean_delta,
        replicates=SMOKE_REPLICATES,
        seed=5,
    )
    assert abs(interval.point - 0.2) < 1e-9
    assert interval.excludes_zero_above


def test_paired_bootstrap_does_not_claim_a_difference_when_there_is_none():
    a = _items({f"d{i}": [0.5] for i in range(25)})
    interval = paired_cluster_bootstrap(
        a,
        a,
        document_key=lambda r: r.document_id,
        statistic=_mean_delta,
        replicates=SMOKE_REPLICATES,
        seed=6,
    )
    assert interval.point == 0.0
    assert interval.excludes_zero_above is False


def test_wilson_interval_is_bounded():
    lo, hi = wilson_interval(0, 10)
    assert lo >= 0.0 and hi <= 1.0
