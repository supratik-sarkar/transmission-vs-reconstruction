#!/usr/bin/env bash
# Create the private runtime workspace.
#
# No path is hard-coded. The location comes from HANDOFF_PRIVATE_HOME, or from
# the first argument, or from a neutral per-user default. The workspace is
# deliberately NOT a Git repository and must live outside this checkout.
set -euo pipefail

PRIVATE_HOME="${1:-${HANDOFF_PRIVATE_HOME:-$HOME/.handoff-fidelity}}"
PUBLIC_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$PRIVATE_HOME" in
  "$PUBLIC_REPO"|"$PUBLIC_REPO"/*)
    echo "refusing: the private workspace must live OUTSIDE the public repository" >&2
    echo "  requested: $PRIVATE_HOME" >&2
    exit 2
    ;;
esac

if [ -e "$PRIVATE_HOME/.git" ]; then
  echo "refusing: $PRIVATE_HOME contains .git. The runtime workspace must remain non-Git," >&2
  echo "because credentials, raw sources and unpublished outputs live there." >&2
  exit 2
fi

echo "private workspace: $PRIVATE_HOME"

mkdir -p \
  "$PRIVATE_HOME"/configs/baselines \
  "$PRIVATE_HOME"/data/{raw,interim,processed,calibration,source_pool,stage1,stage2_dev,stage2_test} \
  "$PRIVATE_HOME"/{source_manifests,calibration,preregistration,protocol_freeze,test_freeze} \
  "$PRIVATE_HOME"/third_party/{provence,queryselect,cpc,llmlingua2,recomp} \
  "$PRIVATE_HOME"/envs \
  "$PRIVATE_HOME"/runs/{calibration,baseline_reproduction,stage1,stage2_dev,stage2_test,experiment_c,multihop} \
  "$PRIVATE_HOME"/{cache,logs,artifacts,tables,figures,manuscript_exports}

if [ ! -f "$PRIVATE_HOME/.env" ]; then
  cp "$PUBLIC_REPO/.env.example" "$PRIVATE_HOME/.env"
  chmod 600 "$PRIVATE_HOME/.env"
  echo "created $PRIVATE_HOME/.env from the public template (mode 600)"
  echo "fill in credentials there. Never copy it into the repository."
fi

cat <<EOF

Next:

  export HANDOFF_PRIVATE_HOME="$PRIVATE_HOME"
  python3.12 -m venv "\$HANDOFF_PRIVATE_HOME/.venv-handoff-fidelity"
  source "\$HANDOFF_PRIVATE_HOME/.venv-handoff-fidelity/bin/activate"
  pip install -e "$PUBLIC_REPO[dev]"
  handoff doctor
  handoff self-test

The workspace is intentionally not a Git repository. Do not run 'git init' in it.
EOF
