"""The public/private boundary guard.

The private runtime workspace must never become a Git repository and must never
sit inside the public checkout. Both conditions are checked mechanically,
because either one turns a single ``git add -A`` into a data disclosure.
"""

from __future__ import annotations

from pathlib import Path


class PrivateBoundaryError(RuntimeError):
    pass


def assert_private_workspace(private_home: Path, public_repo: Path | None = None) -> None:
    private_home = Path(private_home).expanduser().resolve()

    if public_repo is not None:
        public = Path(public_repo).resolve()
        if private_home == public or public in private_home.parents:
            raise PrivateBoundaryError(
                "the private runtime workspace is inside the public repository; move it "
                "outside before writing any credential, raw source or run output"
            )

    if (private_home / ".git").exists():
        raise PrivateBoundaryError(
            "the private runtime workspace contains a .git directory. It must remain "
            "non-Git: credentials, raw sources and unpublished outputs live here."
        )


def assert_no_env_in_public(public_repo: Path) -> None:
    public = Path(public_repo).resolve()
    offenders = [
        p
        for p in public.rglob(".env*")
        if p.is_file() and p.name != ".env.example" and ".git" not in p.parts
    ]
    if offenders:
        raise PrivateBoundaryError(
            "environment files found inside the public repository: "
            + ", ".join(str(p.relative_to(public)) for p in offenders)
        )
