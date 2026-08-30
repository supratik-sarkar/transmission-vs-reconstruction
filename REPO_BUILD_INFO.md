# Repository build information

Generated: 2026-08-31

Validation performed in the artifact-generation runtime:

- Python source compilation: PASS
- Bash syntax checks: PASS
- Colab notebook JSON validation: PASS
- Deterministic unit/self-tests: **10 passed**
- Stage-1 dry-run: PASS; no model call made

Not validated in this runtime:

- editable installation under Python 3.12.13 (the artifact runtime uses a different Python version);
- Ruff/mypy execution, because those packages are not installed and this runtime has no package-network access;
- any provider API call;
- SEC retrieval;
- MPS/CUDA inference;
- macOS-specific pyenv/venv creation.

The supplied macOS bootstrap creates the requested Python 3.12.13 private venv on the user's M4 Pro and should be followed by `make check` in that environment.
