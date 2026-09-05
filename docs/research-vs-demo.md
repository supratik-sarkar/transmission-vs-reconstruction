# Research mode and demo mode

The two modes differ in ways that are scientific, not cosmetic, so the mode is a
type rather than a string comparison scattered through the code.

| Capability | `RESEARCH_MODE` | `DEMO_MODE` |
|---|---|---|
| Guardrails on the inference path | **never** | never |
| Guardrails at a demo perimeter | no | optional, off by default |
| External tracing (LangSmith) | refused | opt-in |
| Browser may mutate frozen parameters | no | no |
| Browser may launch the sealed final test | no | no |
| Browser may launch a synthetic run | no | yes |
| Graph topology mutable | no | no |

## Why guardrails are excluded from the inference path

Guardrails can modify or block model traffic. Between the relay and the receiver
that would mean the measured message is not the message the relay produced,
silently invalidating $T$, $R^-$, $D^+$ and everything built on them.

The boundary is enforced by position, not only by mode: the check refuses every
position in the scientific inference path **even in demo mode**, so a demo
configuration cannot leak into a research run.

## Why external tracing is off by default

Enabling it would send trace content to a third party. In research mode that
could mean real source text and real model output leaving the machine merely
because the orchestration library supports it. Research mode therefore refuses to
enable it, and the default in both modes is off.

## Demo output has no evidentiary status

Every synthetic run is labelled `SYNTHETIC - MOCK RUN - NOT A SCIENTIFIC RESULT`
and carries `evidentiary_status: NONE` through the API into the UI. Fixture
numbers are fabricated to exercise the wiring and prove nothing.
