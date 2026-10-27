# Run record — Apache RocketMQ, 27 Oct 2026

First vertical slice: SCIP + tree-sitter → merged evidence → deterministic HLD/LLD.

## Inputs

| Item | Value |
|---|---|
| Repository | `apache/rocketmq` |
| Tag | `rocketmq-all-5.5.1` |
| Commit | `efa1be59d6fc747ad220f036c86030f05f0419f9` |
| Java files | 2,254 in checkout; 2,265 SCIP documents after build; 1,550 main-source after filters |
| Licence | Apache-2.0 |
| SCIP index | `artifacts/rocketmq.scip` (86 MB) |
| Evidence schema | `docs/evidence-schema.v1.json` (draft 1.0.0) |

## Command

```bash
./scripts/index_rocketmq.sh
./scripts/run_rocketmq.sh
```

## Adapter results

| Stage | Entities | Edges | Notes |
|---|---:|---:|---|
| SCIP (internal, main only) | 34,010 | 86,517 | compiler-accurate definitions/references; calls inferred from symbol kind |
| tree-sitter | 31,040 | 33,574 | syntax entities, imports, unique-name calls, extends/implements; generated/test excluded |
| Merged (validated) | 38,789 | 109,647 | union; no conflicts emitted in this run |

**Overlap:** entity Jaccard 0.677; edge Jaccard 0.095. These are adapter-overlap metrics,
not accuracy. The adapters cover different relation types (SCIP calls/uses; tree-sitter
imports/extends), and neither is ground truth.

**Coverage:** 1,550 main files, 1,549 analyzed, 1 skipped; 23 production + 196 example `main`
entry points; no data-store evidence extracted (recorded as an unknown). HLD witnesses cover
67 files (4.3%) — a capped sample, not exhaustive coverage.

## HLD baseline

16 module containers; 40 aggregated cross-module edges.

| Container | Classes | Methods | Files |
|---|---:|---:|---:|
| broker | 890 | 3,240 | 167 |
| proxy | 503 | 2,483 | 169 |
| remoting | 398 | 3,911 | 323 |
| store | 341 | 4,280 | 152 |
| client | 312 | 3,313 | 160 |
| common | 285 | 2,492 | 184 |
| tools | 242 | 1,920 | 122 |
| auth | 220 | 769 | 59 |

Top edges: broker→remoting (7,840 / 4,234 witnesses), broker→common (6,667 / 4,052),
client→remoting (5,214 / 3,682), client→common (3,668 / 2,216).

Artifacts: `artifacts/hld/c4.model.json`, `artifacts/hld/hld.mmd`.

## LLD baseline — namesrv

34 classes, 10 flows, 500 serialized edges (563 total) in the slice.

Top classes by degree: `NamesrvController` (21), `BrokerAddrInfo` (16),
`RouteInfoManager` (9), `BrokerLiveInfo` (8), `ClientRequestProcessor` (5),
`BatchUnregistrationService` (4), `KVConfigManager` (4).

Flows now include `registerBroker` (11/9 steps), `brokerHeartbeat` (6),
`getRouteInfoByTopic` (8/7), `processRequest` (29/9), `initialize` (30), and
`start` (2/33). `main` is listed as an untraced surface because its call edge is unresolved.
Every step beyond depth 0 carries `call_site` evidence.

Artifacts: `artifacts/lld/namesrv.lld.json`, `broker.lld.json`, `remoting.lld.json`.

## What this proves / does not prove

**Proves:** two independent adapters can emit the same schema, validate, merge, and produce
evidence-linked HLD/LLD baselines for a 2,265-file Java repository in ~44 seconds
(excluding the one-time Maven/SCIP build).

**Does not prove:** boundary correctness, flow completeness, or migration readiness. There
are no golden labels yet; data stores are not extracted; dynamic dispatch is not traced;
COBOL, SQL/PL-SQL, React/TypeScript, and C# are out of this slice.

## Review outcomes

The HLD review found generated-source leakage, truncated/example-dominated entry points,
inconsistent unknown counts, and missing outline artifacts. The LLD review found 23 generated
classes, 45 phantom `call` methods, missing `NamesrvStartup`, callee-not-call-site evidence,
and an edges-total/serialized mismatch. All were fixed or explicitly recorded; the remaining
gaps are listed in `docs/agent-review-outcomes.md`.

## Next

1. Run the `hld-architect` and `lld-analyst` reviews over these artifacts.
2. Label one golden repository (boundaries, top flows, states).
3. Measure edge/boundary F1 and evidence coverage against those labels.
4. Add data-store extraction and runtime traces for critical flows.
