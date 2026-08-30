# Transmission vs Reconstruction

> **Causal measurement of what actually survives an LLM-to-LLM handoff.**

This repository is the public, GitHub-safe implementation for the research project behind the manuscript **“What Survived the Handoff? Causally Separating Transmission from Reconstruction in Multi-Agent LLM Workflows.”**

The central question is simple:

> If a downstream agent gives the correct answer, did that information actually survive the handoff, or did the receiver reconstruct what the sender had already dropped?

A relay can send only _“North America margins improved”_ while a receiver outputs _“North America margins improved by 6.2% in FY2023.”_ Endpoint accuracy alone cannot distinguish successful transmission from successful reconstruction.

The project therefore treats the relay as a causal assignment mechanism and measures:

- **focal-omission reconstruction** `R^-`: recovery when the focal atom is absent but the rest of the natural handoff is retained;
- **explicit-transmission recovery** `D^+`;
- **availability surplus** `Δ^avail = D^+ - R^-`;
- the endpoint-fidelity decomposition

  `A = R̄₀ + T̄ Δ̄ + Cov(T, Δ)`;
- observational selection bias from studying only naturally omitted atoms;
- matched prior-access effects under a fixed handoff skeleton;
- post-gate budget-neutral targeting and multi-hop behavior.

## Current research status

- **Manuscript scientific architecture:** frozen at v2.7.
- **Experimental execution protocol:** **not yet binding**. The preregistration is still being hardened before any Stage-1 experimental model call.
- **Stage 1:** planned 100-document discovery pilot.
- **Stage 2:** planned 300 new-document confirmatory run if a pre-registered gate clears.
- **Important:** this repository deliberately refuses a real Stage-1 run unless the private workspace contains a valid freeze record.

See [`EXPERIMENTAL_DESIGN_AND_EXECUTION_STATUS.md`](EXPERIMENTAL_DESIGN_AND_EXECUTION_STATUS.md) for the full design, current blockers, and MacBook/Colab execution plan.

---

## 1. Public repo vs private runtime workspace

The project intentionally uses **two directories** on the research machine.

### Public Git repository

```text
~/Desktop/My_Git/transmission-vs-reconstruction
```

Contains only:

- source code;
- tests;
- prompts/specifications once frozen;
- public documentation;
- preregistration templates and public freeze metadata;
- no credentials;
- no raw/private data;
- no unpublished run outputs.

### Private, non-Git runtime workspace

```text
~/Desktop/handoff-fidelity
```

Contains:

- `.venv-handoff-fidelity`;
- `.env` and private API credentials;
- raw SEC/source files;
- calibration material;
- model outputs;
- run ledgers;
- intermediate artifacts;
- private freeze material before public release.

**Never initialize Git inside `~/Desktop/handoff-fidelity`.**

The code defaults mutable outputs to the private workspace through `HANDOFF_PRIVATE_HOME`.

---

## 2. Fast installation on macOS (Apple Silicon / M4 Pro)

### Prerequisites

- macOS on Apple Silicon;
- Homebrew;
- `git`;
- Python **3.12.13** (the bootstrap uses `pyenv` to pin it exactly).

### A. Put the public repo in the requested location

```bash
mkdir -p ~/Desktop/My_Git
cd ~/Desktop/My_Git
unzip transmission-vs-reconstruction.zip
cd transmission-vs-reconstruction
```

If this repo is already on GitHub:

```bash
mkdir -p ~/Desktop/My_Git
cd ~/Desktop/My_Git
git clone https://github.com/supratik-sarkar/transmission-vs-reconstruction.git
cd transmission-vs-reconstruction
```

### B. Create the private workspace and venv

```bash
bash scripts/bootstrap_macos_private.sh
```

This creates:

```text
~/Desktop/handoff-fidelity/
└── .venv-handoff-fidelity/
```

using Python 3.12.13, then installs this public repo in editable mode.

Activate it later with:

```bash
source ~/Desktop/handoff-fidelity/.venv-handoff-fidelity/bin/activate
```

### C. Verify the installation

```bash
handoff doctor
pytest -q
```

A healthy fresh install should pass all deterministic unit/self-tests without making any LLM call.

---

## 3. Private API keys — never commit them

The bootstrap creates:

```text
~/Desktop/handoff-fidelity/.env
```

from the private template. Put credentials only there, for example:

```dotenv
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
SEC_USER_AGENT="Your Name your.email@example.com"
```

The public repo contains **no live secrets** and `.gitignore` blocks common secret/data paths. The CLI also warns if the configured private workspace is inside the public repository.

Use only providers/models that are explicitly pinned in the final preregistration. Provider adapters are scaffolding, not permission to change models after freeze.

---

## 4. Repository layout

```text
transmission-vs-reconstruction/
├── README.md
├── EXPERIMENTAL_DESIGN_AND_EXECUTION_STATUS.md
├── pyproject.toml
├── Makefile
├── CITATION.cff
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
├── .gitignore
├── .pre-commit-config.yaml
├── src/handoff_fidelity/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── sampling.py
│   ├── matcher.py
│   ├── editor.py
│   ├── estimands.py
│   ├── gates.py
│   ├── bootstrap.py
│   ├── integrity.py
│   ├── runner.py
│   └── providers/
├── protocol/
│   ├── prompts/
│   ├── specs/
│   ├── randomisation/
│   └── templates/
├── docs/
│   ├── preregistration/
│   └── architecture/
├── scripts/
├── tests/
├── notebooks/
└── .github/workflows/
```

---

## 5. Safe first commands

### Inspect the private/public boundary

```bash
handoff doctor
```

### Run design self-tests

```bash
handoff self-test
```

### Validate a protocol manifest

```bash
handoff protocol verify --private-home ~/Desktop/handoff-fidelity
```

### Dry-run Stage 1 without any provider call

```bash
handoff stage1 --dry-run
```

### Real Stage 1

A real Stage-1 call is intentionally guarded. It requires a valid private freeze record and explicit opt-in:

```bash
handoff stage1 --execute
```

If the protocol is not frozen, the command exits before any provider request.

---

## 6. Experimental workflow at a glance

### Experiment A — Natural relay decomposition

1. construct the exact relay-visible source `X_i`;
2. build a verified Tier-1 atom inventory from that same source;
3. sample focal atoms **before** relay generation;
4. run the natural relay and observe transmission `T_iz`;
5. query the natural receiver output;
6. create only the missing availability arm:
   - transmitted atom → delete it;
   - omitted atom → insert it;
7. recover/estimate `R^-`, `D^+`, `Δ^avail`;
8. compute the weighted natural decomposition and observational-bias diagnostic.

### Experiment B — Matched prior-access contrast

Hold a matched non-focal handoff skeleton fixed while changing the natural versus prior-blocked identity/value mapping, with the focal target absent in both arms. This isolates prior-assisted reconstruction from changed message composition.

### Experiment C — Post-gate budget-neutral targeting

Only after the discovery gate passes. A smaller fully instrumented candidate set receives matched-length insert/evict swaps to estimate `Δ^budget`. First-order targeting metrics are explicitly not treated as the true joint causal optimum unless interaction diagnostics support approximate additivity.

### Multi-hop extension

Post-gate, repeat at handoff depths `h ∈ {1,2,3,5}` to test whether endpoint fidelity can remain high while actually transmitted content deteriorates.

---

## 7. Stage gates

The current draft protocol retains the following planned discovery logic, but the preregistration is **not binding until final freeze**:

- prior-access effect gate: `ΔR_prior^matched ≥ 0.10` on a predeclared eligible class;
- natural reconstruction contribution gate: `E[(1-T)R^-] ≥ 0.10`;
- proceed if **either** clears;
- halt if **both** fail.

No p-value gate should substitute for these predeclared effect-size gates.

---

## 8. M4 Pro vs Colab A100

### MacBook Pro M4 Pro

Best for:

- environment/bootstrap;
- source ingestion and manifests;
- deterministic atom/matcher/editor tests;
- API-based relay/receiver runs;
- Stage-1 orchestration if providers are remote APIs;
- analysis, bootstrap, tables, plots;
- small open-weight model checks through MPS.

### Google Colab Pro / A100

Best for:

- larger open-weight relay/receiver models;
- repeated local stochastic prior probes;
- high-throughput model inference when API calls are not used;
- larger Stage-2/depth sweeps;
- CUDA-only libraries.

The included notebook template uses Colab Secrets / environment variables and never embeds API keys in the notebook.

---

## 9. Reproducibility and integrity

The intended freeze chain is non-circular:

1. freeze prompts/specs/code/support/source artifacts;
2. hash them into an artifact manifest;
3. finalize the preregistration with the artifact-manifest hash;
4. create a separate freeze record containing preregistration hash, manifest hash, source-pool hash, Git commit, model versions, and UTC timestamp;
5. verify before Stage 1;
6. record every deviation in `DEVIATIONS.md`.

The CLI's `protocol verify` command implements the mechanical checks; scientific approval remains a human responsibility.

---

## 10. Development

```bash
source ~/Desktop/handoff-fidelity/.venv-handoff-fidelity/bin/activate
pip install -e '.[dev]'
ruff check .
mypy src
pytest -q
```

Optional provider/local-model extras:

```bash
pip install -e '.[openai]'
pip install -e '.[anthropic]'
pip install -e '.[gemini]'
pip install -e '.[hf]'
```

---

## 11. Academic citation

See [`CITATION.cff`](CITATION.cff). Replace anonymous/draft metadata when the paper is public.

---

## 12. What this repository does **not** do automatically

It does not:

- invent the final model/version strings;
- inspect experimental outcomes before freeze;
- replace human atom/matcher audits;
- decide whether a protocol deviation is scientifically acceptable;
- make Stage-1 provider calls unless explicitly enabled after freeze;
- store any private API credential in Git.

Those boundaries are intentional.
