from pathlib import Path

import pytest

from handoff_fidelity.private_guard import PrivateBoundaryError, assert_private_workspace


def test_private_home_cannot_be_inside_public(tmp_path: Path) -> None:
    public = tmp_path / "repo"
    private = public / "private"
    private.mkdir(parents=True)
    with pytest.raises(PrivateBoundaryError):
        assert_private_workspace(private, public)
