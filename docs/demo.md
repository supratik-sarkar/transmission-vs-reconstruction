# Demo

A complete synthetic route with no network, no credential and no provider
account.

```bash
pip install -e ".[app,dev]"
HANDOFF_APP_MODE=DEMO python -m uvicorn handoff_api.app:create_app --factory \
  --host 127.0.0.1 --port 8099

cd apps/web && npm ci && npm run dev      # http://127.0.0.1:5173
```

Press **Run synthetic demo**.

## What it shows

The default seed is chosen because it surfaces all three headline behaviours in
one three-focal run:

* an atom **transmitted** and used
* an atom **omitted but reconstructed** from the receiver's prior knowledge
* an atom **omitted and lost**

giving $A = 2/3$ with $C_{\mathrm{comm}} = 0$ and $C_{\mathrm{recon}} = 2/3$:
every bit of endpoint correctness came from reconstruction and none from
communication. That is the phenomenon the project exists to measure, visible in a
single screen.

**The numbers are fabricated.** They are chosen to make the demo legible and they
prove nothing. Every synthetic run is labelled
`SYNTHETIC - MOCK RUN - NOT A SCIENTIFIC RESULT` and carries
`evidentiary_status: NONE` from the estimator through the API into the UI.

## Without the frontend

```bash
python -c "
from handoff_fidelity.orchestration.mock_pipeline import run_mock_pipeline
r = run_mock_pipeline(seed=2)
print(r.marker); print(r.state.decomposition)"
```

## What the demo cannot do

It cannot start a real stage, mutate a frozen parameter, enable guardrails on the
inference path, or launch the sealed final test. Those are refused by policy and,
more fundamentally, are not exposed by the API.
