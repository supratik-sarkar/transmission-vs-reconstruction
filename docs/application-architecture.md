# Application architecture

The application stack **wraps** the scientific core. It never redefines it.

```
                         React 19 UI
                              │
                        HTTP / SSE / WS
                              │
                           FastAPI
                              │
             ┌────────────────┼─────────────────┐
             │                │                 │
         LangGraph          OPA             OpenTelemetry
       orchestration       policy          observability
             │
             ▼
      Scientific core  (deterministic, independently tested)
             │
             ▼
      Provider protocol
   ┌─────────┼─────────┬──────────┐
 OpenAI   DeepSeek  Anthropic   Gemini
```

The diagram is architectural. **Only the scientific core sits on the causal
measurement path.** Policy, telemetry and the UI observe or gate; none of them
transforms a message that is being measured.

## The boundary

These quantities are computed in exactly one place — the tested scientific
package — and passed through unchanged:

$$
T_{iz},\qquad
R^-_{iz} = \mathbb{E}\!\left[Y_{iz}(0; M^{\mathrm{obs}}_{i,-z})\right],\qquad
D^+_{iz} = \mathbb{E}\!\left[Y_{iz}(1; M^{\mathrm{obs}}_{i,-z})\right],\qquad
\Delta^{\mathrm{av}}_{iz} = D^+_{iz} - R^-_{iz}.
$$

$$
A = \bar R_0 + \bar T\bar\Delta + \operatorname{Cov}\!\left(T, \Delta^{\mathrm{av}}\right),
\qquad
C_{\mathrm{comm}} = A - \bar R_0,
\qquad
C_{\mathrm{recon}} = \mathbb{E}\!\left[(1-T)R^-\right].
$$

No orchestration, policy, telemetry or presentation component may alter them.
The browser does not recompute any of them: it renders what the backend
delivered.

## Layers

| Layer | Package | Responsibility |
|---|---|---|
| Contracts | `app_contracts/` | event envelope, modes, error taxonomy |
| Orchestration | `orchestration/` | fixed-topology graph over existing primitives |
| Providers | `providers/` | protocol, adapters, capability registry, call ledger, redaction |
| Telemetry | `telemetry/` | OTel spans, LangSmith gate, guardrail boundary |
| Policy | `policy/` | lifecycle decisions, OPA client, fail-closed mirror |
| Calibration | `calibration/` | the four frozen selection rules |
| API | `apps/api/` | read-only HTTP surface, SSE/WS streaming |
| Web | `apps/web/` | research instrument UI |

## Optional by construction

The scientific core depends on the standard library and NumPy. Every heavyweight
component degrades rather than crashing:

| Missing | Behaviour |
|---|---|
| `langgraph` | deterministic sequential executor, same nodes, same order |
| `opentelemetry` | in-memory tracer, spans still recorded |
| `opa` binary | Python mirror decides, and it is fail-closed |
| provider SDK | adapter reports `SDK_MISSING`, no import-time crash |

This is not defensive padding. It means the scientific path can be executed and
tested with no orchestration, telemetry or policy dependency installed at all,
which is what keeps the core independently verifiable.

## What the API deliberately does not expose

There is **no endpoint that starts a real scientific stage**. Development
execution is CLI-controlled; the sealed final test additionally requires a valid
freeze record. A browser button that could start either would turn the frontend
into a route around the protocol.
