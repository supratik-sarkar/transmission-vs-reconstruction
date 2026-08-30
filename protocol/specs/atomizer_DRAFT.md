# Atomizer specification — DRAFT / UNFROZEN

The experimental sampling frame is the **human-verified Tier-1 inventory extracted from exactly the relay-visible source text**.

## Relay-visible source

`X_i` is the exact truncated source passed to the relay. No focal atom may originate outside `X_i`.

## Tier-1 roles

- `entity`
- `scope`
- `period`
- `numeric`
- `provenance`

## Required inventory columns

`document_id, atom_id, role, value, source_text, source_start, source_end, human_verified`

## Rules

1. Proposal generation may be deterministic or model-assisted, but the proposal method/model/prompt must be frozen.
2. Human verification happens before focal sampling.
3. Duplicates referring to the same source fact are merged under a frozen rule.
4. A document is Stage-eligible only after verification establishes >=12 Tier-1 atoms and >=3 populated strata on `X_i`.
5. The primary causal receiver must never define its own evaluation atoms.
