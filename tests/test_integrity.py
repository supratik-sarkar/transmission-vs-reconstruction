from pathlib import Path

from handoff_fidelity.integrity import verify_freeze


def test_missing_freeze_refuses(tmp_path: Path) -> None:
    ok, failures = verify_freeze(tmp_path)
    assert not ok
    assert failures
