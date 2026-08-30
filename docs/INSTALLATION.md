# Installation guide

## Requested macOS layout

```text
~/Desktop/My_Git/transmission-vs-reconstruction   # public Git repo
~/Desktop/handoff-fidelity                        # private non-Git workspace
```

The private workspace owns the exact Python 3.12.13 venv:

```text
~/Desktop/handoff-fidelity/.venv-handoff-fidelity
```

Run `scripts/bootstrap_macos_private.sh` from the public checkout. It installs Python 3.12.13 via pyenv when needed, creates the venv, creates the private directory tree, writes a mode-600 `.env`, and installs the public package editable.

## Why the venv is not inside the Git checkout

The runtime environment, API keys, data, caches, and outputs all belong to the non-Git execution boundary. The public code remains clean and reproducible.

## Optional provider extras

Install only what the frozen experiment actually uses:

```bash
pip install -e '.[openai]'
pip install -e '.[anthropic]'
pip install -e '.[gemini]'
pip install -e '.[hf]'
```

Do not infer a scientifically valid model choice from the existence of an adapter.
