#!/usr/bin/env bash
set -euo pipefail

PUBLIC_REPO="${PUBLIC_REPO:-$HOME/Desktop/My_Git/transmission-vs-reconstruction}"
PRIVATE_HOME="${HANDOFF_PRIVATE_HOME:-$HOME/Desktop/handoff-fidelity}"
PYTHON_VERSION="3.12.13"
VENV="$PRIVATE_HOME/.venv-handoff-fidelity"

echo "Public repo : $PUBLIC_REPO"
echo "Private home: $PRIVATE_HOME"
echo "Python      : $PYTHON_VERSION"

if [[ ! -d "$PUBLIC_REPO" ]]; then
  echo "ERROR: public repo not found at $PUBLIC_REPO" >&2
  exit 2
fi

if [[ -d "$PRIVATE_HOME/.git" ]]; then
  echo "ERROR: $PRIVATE_HOME contains .git; private workspace must remain non-Git." >&2
  exit 2
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "ERROR: Homebrew is required. Install it first from https://brew.sh" >&2
  exit 2
fi

if ! command -v pyenv >/dev/null 2>&1; then
  brew install pyenv
fi

pyenv install -s "$PYTHON_VERSION"
mkdir -p "$PRIVATE_HOME"
cd "$PRIVATE_HOME"
printf '%s\n' "$PYTHON_VERSION" > .python-version

PYENV_VERSION="$PYTHON_VERSION" pyenv exec python -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$PUBLIC_REPO[dev]"

mkdir -p data/{raw,interim,processed} runs cache logs calibration source_manifests protocol_freeze secrets

if [[ ! -f .env ]]; then
  cat > .env <<ENV
HANDOFF_PRIVATE_HOME=$PRIVATE_HOME
HANDOFF_RELAY_PROVIDER=mock
HANDOFF_RECEIVER_PROVIDER=mock
HANDOFF_RELAY_MODEL=UNFROZEN
HANDOFF_RECEIVER_MODEL=UNFROZEN
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
SEC_USER_AGENT="Your Name your.email@example.com"
ENV
  chmod 600 .env
fi

cat > .gitignore <<'GITIGNORE'
*
!.gitignore
GITIGNORE

printf '\nBootstrap complete. Activate with:\n  source %q\n' "$VENV/bin/activate"
printf 'Then run:\n  handoff doctor\n  handoff self-test\n'
