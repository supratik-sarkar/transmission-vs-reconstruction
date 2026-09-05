# Provider interface

The scientific core never imports a vendor SDK. It sees one protocol:

```python
compress/generate(request: GenerationRequest) -> GenerationResponse
```

so swapping a provider cannot change a measurement path, and a missing SDK
degrades to `NOT_CONFIGURED` instead of an import-time crash.

## Adapters

| Provider | Transport | Status shipped |
|---|---|---|
| OpenAI | official SDK, Responses API | integration point |
| DeepSeek | OpenAI-compatible client | integration point |
| Anthropic | official SDK | integration point |
| Gemini | official SDK | integration point |
| Mock | in-repo, deterministic | ready |

DeepSeek is a **separate adapter** although its HTTP surface is
OpenAI-compatible. Treating them as one would erase the per-provider metadata the
ledger needs and would let an OpenAI-specific assumption silently govern a
DeepSeek run.

## Preflight, in order

1. adapter enabled
2. **model pinned** — a moving alias makes measurement unreproducible
3. SDK installed
4. credential present in the environment
5. network explicitly allowed

Every check fails closed. Ordering matters: pinning is verified before anything
can reach a provider, so an unpinned run cannot spend a token.

## Capabilities

Every field defaults to `UNKNOWN` and is resolved from official documentation
during model pinning. A guessed `seed_support` would silently change which
decoder regime we believe we are in.

## The call ledger

Append-only JSONL. Each attempt records call id, run id, provider, requested and
returned model, attempt number, timestamps, latency, status, prompt/request/
response **hashes**, provider request id, token usage and error class.

Raw prompts and responses live in the private workspace. Content is hashed here;
the browser never receives a raw provider payload.

Retries are bounded, deterministic and recorded per attempt. There is no
semantic retry: retrying because an answer looked wrong would contaminate the
experiment.

## Secrets

Read from the environment only. Never accepted as an argument, written to disk,
logged, placed in an exception, attached to a span, or included in a repr — the
provider classes override `__repr__` for that reason. The status shape that
reaches the UI carries a boolean and nothing else: no key, no prefix, no suffix,
no length.
