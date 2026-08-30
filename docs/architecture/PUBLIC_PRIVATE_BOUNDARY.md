# Public/private architecture

## Public Git checkout

`~/Desktop/My_Git/transmission-vs-reconstruction`

Immutable/reviewable code and public documentation only.

## Private runtime home

`~/Desktop/handoff-fidelity`

No `.git` directory. Contains secrets, source data, calibration artifacts, and runs.

The private venv installs the public checkout editable. This avoids code duplication while keeping credentials/results physically outside Git.

### Required environment

```bash
export HANDOFF_PRIVATE_HOME="$HOME/Desktop/handoff-fidelity"
```

API keys belong only in `$HANDOFF_PRIVATE_HOME/.env` or a provider/Colab secret manager.
