# Legacy Lens

Evidence-first recovery of HLD and LLD from an existing codebase, with an open-source Java
vertical slice.

**Status:** first vertical slice runs end to end on Apache RocketMQ. The measured score is still
TBD; this is a baseline, not a validated product.

**Status page:** [`docs/implementation-status.html`](docs/implementation-status.html) — what was
achieved, the last run metrics, review findings, limitations, and next steps.

**Rendered docs:** <https://kosanamsandeep.github.io/design_agents/>

## What is implemented

| Component | Path | State |
|---|---|---|
| Evidence schema v1 draft | `docs/evidence-schema.v1.json` | contract tests pass |
| Semantic validator | `legacy_lens/validation.py` | validates schema + referential integrity |
| SCIP Java adapter | `legacy_lens/adapters/scip_java.py` | definitions, references, calls/uses |
| tree-sitter Java adapter | `legacy_lens/adapters/tree_sitter_java.py` | syntax entities, imports, calls, routes |
| Merge layer | `legacy_lens/merge.py` | unions evidence, preserves conflicts |
| HLD baseline | `legacy_lens/architecture.py` | module containers, counted edges, Mermaid |
| LLD baseline | `legacy_lens/architecture.py` | per-context classes, flows, seams |
| Pipeline CLI | `legacy_lens/cli.py` | `scip`, `treesitter`, `merge`, `hld`, `lld`, `run` |
| HLD skill + agent | `.claude/skills/hld-synthesis/`, `.claude/agents/hld-architect.md` | read-only synthesis |
| LLD skill + agent | `.claude/skills/lld-synthesis/`, `.claude/agents/lld-analyst.md` | per-context synthesis |
| Install record | `installations.md` | exact versions and commands |

## Test repository

- [`apache/rocketmq`](https://github.com/apache/rocketmq)
- Tag `rocketmq-all-5.5.1`
- Commit `efa1be59d6fc747ad220f036c86030f05f0419f9`
- Source snapshot vendored at `testdata/rocketmq` (`.lens-commit` = the pinned SHA); build
  outputs are excluded. 2,254 Java files in the checkout; 2,265 SCIP documents after the Maven
  build; 1,550 main-source files after the adapter filters.
- Apache-2.0.

## Run it

```bash
# 1. one-time toolchain setup (see installations.md)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# scip-java v0.13.2 binary at ~/.local/bin/scip-java

# 2. index the frozen commit (Maven; first run downloads dependencies)
./scripts/index_rocketmq.sh

# 3. adapters -> merge -> HLD -> LLD
./scripts/run_rocketmq.sh
```

Or step by step:

```bash
.venv/bin/python -m legacy_lens.cli scip --repo testdata/rocketmq \
  --index artifacts/rocketmq.scip --out artifacts/evidence.scip.json
.venv/bin/python -m legacy_lens.cli treesitter --repo testdata/rocketmq \
  --out artifacts/evidence.treesitter.json
.venv/bin/python -m legacy_lens.cli merge \
  --inputs artifacts/evidence.scip.json artifacts/evidence.treesitter.json \
  --out artifacts/code.graph.json
.venv/bin/python -m legacy_lens.cli hld --model artifacts/code.graph.json --out-dir artifacts/hld
.venv/bin/python -m legacy_lens.cli lld --model artifacts/code.graph.json \
  --module namesrv --out-dir artifacts/lld
```

## First-slice results

| Metric | Value |
|---|---:|
| SCIP entities / edges | 34,010 / 86,517 |
| tree-sitter entities / edges | 31,040 / 33,574 |
| Merged entities / edges | 38,789 / 109,647 |
| Entity overlap (Jaccard) | 0.677 |
| Edge overlap (Jaccard) | 0.095 |
| HLD containers / edges | 16 / 40 |
| LLD `namesrv` classes / flows | 34 / 10 |
| Entry points | 23 production + 196 example `main` methods |
| HLD witness coverage | 67 files (4.3% of analyzed) — samples, not exhaustive |
| Analyzed files | 1,550 total, 1,549 analyzed, 1 skipped |
| End-to-end run time | ~44 s (index build separate) |

Artifacts:

- `artifacts/hld/` — browsable HLD baseline, outline, unknowns, Mermaid, `hld.md`
- `artifacts/lld/` — browsable LLD slices for `namesrv`, `broker`, `remoting`
- `artifacts/manifest.json` — counts, versions, overlap, coverage
- `artifacts/published/*.gz` — compressed SCIP index, SCIP/tree-sitter evidence, and merged graph;
  `artifacts/README.md` explains each file and how to decompress it
- `artifacts/published/SHA256SUMS` — integrity manifest

Top HLD containers by class count: broker (890), proxy (503), remoting (398), store (341),
client (312), common (285), tools (242), auth (220). Top module edges: broker→remoting
(7,840), broker→common (6,667), client→remoting (5,214).

`namesrv` LLD top classes: NamesrvController, BrokerAddrInfo, RouteInfoManager, BrokerLiveInfo,
ClientRequestProcessor. Flows now include broker registration, heartbeat, route lookup, request
processing, and controller startup.

See `docs/run-2026-10-27-rocketmq.md` for the full run record and
`docs/agent-review-outcomes.md` for the two role reviews and their dispositions.

## Known limitations

- **No golden labels yet.** The overlap numbers are not quality scores; they compare two adapters,
  not ground truth. Edge Jaccard is low because the adapters cover different relations (SCIP
  calls/uses; tree-sitter imports/extends) and both are incomplete.
- **Java only.** COBOL, SQL/PL-SQL, React/TypeScript, and C# are not implemented in this slice.
- **No runtime traces.** Dynamic dispatch and DI/reflection can make static flows incomplete.
- **No data-store extraction.** HLD currently records an explicit unknown for data stores.
- **No LLM synthesis yet in the loop.** The deterministic baseline is generated; the
  `hld-architect` and `lld-analyst` agents are defined and ready to refine it.
- **Generated/test sources excluded.** Tests and `target/generated-*` / build outputs are filtered
  out; this is intentional for architecture evidence.
- **States/invariants/seams are not yet extracted.** The LLD emits explicit empty sections and
  unknowns; `namesrv` has no enums/interfaces in this slice.
- **HLD witnesses are samples.** They cover ~4.3% of analyzed files; the source model has
  per-entity/edge evidence, but the HLD does not carry every witness.

## Next

1. Run the `hld-architect` agent over `artifacts/code.graph.json` + baseline, freeze the outline.
2. Run `lld-analyst` on `namesrv` and compare its output to `namesrv.lld.json`.
3. Label one golden repository (boundaries, top flows, states) and add measured metrics.
4. Add the COBOL and SQL/PL-SQL decisions from `docs/delivery-plan-status.html`.
