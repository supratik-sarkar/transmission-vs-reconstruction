from __future__ import annotations

from pathlib import Path


class PrivateBoundaryError(RuntimeError):
    pass


def assert_private_workspace(private_home: Path, public_repo: Path | None = None) -> None:
    private_home = private_home.expanduser().resolve()
    if public_repo is not None:
        public_repo = public_repo.resolve()
        try:
            private_home.relative_to(public_repo)
        except ValueError:
            pass
        else:
            raise PrivateBoundaryError(
                f"Private workspace {private_home} is inside public repo {public_repo}."
            )

    if (private_home / ".git").exists():
        raise PrivateBoundaryError(
            f"{private_home} contains .git. The private runtime workspace must remain non-Git."
        )
