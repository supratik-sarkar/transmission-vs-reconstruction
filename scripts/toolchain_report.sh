#!/usr/bin/env bash
# Record the resolved developer toolchain.
#
# Ruff is deliberately NOT pinned twice. The pre-commit hooks run the project's
# own `ruff` binary (`language: system`), so `ruff check .` and the hook cannot
# disagree: there is one binary, whatever version the environment resolved.
#
# This script prints that version so it can be recorded in a release report.
set -euo pipefail

echo "python:            $(python --version 2>&1)"
echo "python executable: $(python -c 'import sys; print(sys.executable)')"
echo

if command -v ruff >/dev/null 2>&1; then
  echo "ruff (direct):     $(ruff --version)"
  echo "ruff (resolved):   $(command -v ruff)"
else
  echo "ruff:              NOT FOUND - install the dev extra: pip install -e '.[dev]'" >&2
  exit 1
fi

echo "pre-commit ruff:   same binary by construction (repo: local, language: system)"
echo

for tool in mypy pytest pre-commit detect-secrets; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%-18s %s\n' "$tool:" "$($tool --version 2>&1 | head -1)"
  else
    printf '%-18s %s\n' "$tool:" "NOT FOUND"
  fi
done

echo
echo "Verify the two agree on the same source:"
echo "  ruff check ."
echo "  pre-commit run ruff --all-files --verbose"
