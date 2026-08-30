import pytest

from handoff_fidelity.estimands import decompose
from handoff_fidelity.models import AtomCausalRecord, AtomRole


def test_decomposition_identity() -> None:
    records = [
        AtomCausalRecord(
            document_id="d1",
            atom_id="a",
            role=AtomRole.NUMERIC,
            pi=0.5,
            transmitted=1,
            r_minus=0,
            d_plus=1,
        ),
        AtomCausalRecord(
            document_id="d1",
            atom_id="b",
            role=AtomRole.SCOPE,
            pi=0.5,
            transmitted=0,
            r_minus=1,
            d_plus=1,
        ),
        AtomCausalRecord(
            document_id="d2",
            atom_id="c",
            role=AtomRole.PERIOD,
            pi=0.5,
            transmitted=1,
            r_minus=1,
            d_plus=0,
        ),
    ]
    d = decompose(records)
    assert d.endpoint_fidelity == pytest.approx(d.r_bar + d.volume + d.alignment)
    assert d.c_comm == pytest.approx(d.endpoint_fidelity - d.r_bar)
