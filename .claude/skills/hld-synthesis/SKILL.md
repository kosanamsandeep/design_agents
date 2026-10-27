---
name: hld-synthesis
description: Synthesize an evidence-linked C4/HLD from a validated Legacy Lens evidence model. Use for as-is high-level design: containers, data stores, entry points, cross-module edges, and explicit unknowns.
license: internal
metadata:
  owner: platform-engineering
  version: "0.1.0"
allowed-tools: Read Grep Glob Bash
---

# HLD synthesis

## Preconditions

1. `docs/evidence-schema.v1.json` validates the model (`python -m legacy_lens.validation <model>`).
2. The model commit matches the repository commit under review.
3. A deterministic baseline exists (`artifacts/hld/c4.model.json` and `hld.mmd`). Refine it;
   do not start from a blank page.

## Inputs

- Validated evidence model (`artifacts/code.graph.json`).
- Repository facts: build units, deployment manifests, API/queue contracts.
- Deterministic HLD baseline and its Mermaid rendering.
- The maintainer's scope and known constraints.

## Method

1. **Partition by path/build/deploy.** Use directory, Maven/Gradle module, and deploy unit.
   Do **not** use graph communities (Leiden/Louvain) as the primary partition.
2. **Propose 8–12 containers.** For each: module, name, responsibility, owned entities,
   entry points, data stores. Freeze `outline.json` before writing the C4 model.
3. **Build the C4 model.** Containers, external systems, data stores, and directed edges.
   Every container and edge carries `evidence: [{path, span, tool, tool_version, commit}]`
   and `confidence: extracted | inferred | hypothesis`.
4. **Aggregate, don't invent.** HLD edges are counts of evidence edges, not guesses.
   If an edge has no evidence, omit it or record an unknown.
5. **Record unknowns.** Ownership, data ownership, runtime topology, and cross-language
   edges that the evidence cannot prove.
6. **Render from the model.** Mermaid is generated from the structured model, never
   hand-written prose.

## Evidence rules

- No uncited container or edge.
- `extracted` means observed; it does not mean complete.
- `inferred` is a deterministic aggregation; explain the rule.
- `hypothesis` is an LLM proposal and must be reviewed.
- Do not merge entities across languages without a contract/trace.

## Outputs

- `outline.json` (frozen)
- `c4.model.json`
- `hld.mmd`
- `hld.md` (short narrative, every claim linked)
- `unknowns.json`

## Quality gates

- Every container maps to at least one evidence path.
- Every edge has evidence and a count.
- Unsupported claims: 0 in the final artifact (anything unproven becomes an unknown).
- Maintainer sign-off on boundaries before LLD fan-out.

## Refusal rules

- Refuse to present a community-clustered partition as architecture.
- Refuse to output a container with no evidence.
- Refuse to claim runtime flows from static evidence alone.
- Refuse to read the whole repository; use the model and targeted evidence lookups.

## Budget

- Work in 8k–50k-token calls; keep each scope under 80% of the window.
- Read the aggregated model, not the raw 200MB+ graph.
- Return ≤2k tokens plus artifact paths.
