---
name: lld-synthesis
description: Synthesize evidence-linked LLD for one bounded context from a frozen HLD outline and a validated evidence slice. Covers classes/types, call flows, state transitions, seams, and invariants.
license: internal
metadata:
  owner: platform-engineering
  version: "0.1.0"
allowed-tools: Read Grep Glob Bash
---

# LLD synthesis

## Preconditions

- A frozen `outline.json` exists and the context is approved.
- The context slice validates against `docs/evidence-schema.v1.json`.
- The slice commit matches the HLD commit.

## Inputs

- One context slice from the evidence model (never the whole graph).
- The frozen outline and the context's entry points.
- Deterministic LLD baseline (`artifacts/lld/<context>.lld.json`).

## Method

1. **Enumerate entry points.** Public routes, `main`, framework handlers, scheduled jobs.
2. **Build the type model.** Classes, interfaces, enums, fields, methods, parent links.
   Every member comes from the evidence model; do not invent members.
3. **Trace top flows.** Follow `calls` edges from entry points, bounded depth. Produce
   sequence steps with `file:line` evidence. Stop and record an unknown when a call is
   unresolved.
4. **Extract states.** Enums, status fields, transition call sites. Mark inferred
   transitions; require a maintainer to confirm.
5. **Identify seams and invariants.** Interfaces, DI registrations, event boundaries,
   validation sites, DB constraints.
6. **Render from the model.** Class/sequence/state diagrams generated from the JSON.

## Evidence rules

- No invented methods, fields, transitions, or flows.
- A resolvable `file:line` is necessary but not sufficient; state the entailment.
- Cross-context calls are recorded as boundary edges, not inlined.
- Unresolved calls become unknowns, not guesses.

## Outputs

- `lld/<context>.json`
- `lld/<context>.mmd` (class/sequence/state as appropriate)
- `seams.json`
- `unknowns.json`

## Quality gates

- Entry-point and top-flow recall measured against maintainer labels.
- State transitions: ≥90% confirmed by code or maintainer.
- Evidence coverage ≥90%; unsupported claims 0.
- No cross-context reads during synthesis.

## Refusal rules

- Refuse to read another context's slice.
- Refuse to infer a runtime flow from a single static reference.
- Refuse to output a state machine without transition evidence.

## Budget

- One context per call; 8k–50k tokens.
- Cap traversal depth and steps; summarize long chains.
- Return ≤2k tokens plus artifact paths.
