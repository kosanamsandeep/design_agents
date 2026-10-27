# Agent review outcomes — RocketMQ vertical slice

Two read-only role reviews were run over the generated artifacts on 27 Oct 2026:
`hld-architect` and `lld-analyst` (via the `general-purpose` runner, because the project
agent definitions are not registered in the current harness session).

## HLD review — dispositions

| Finding | Disposition |
|---|---|
| Generated/test sources leaked into tree-sitter; `namesrv` witness was a JMH class | Fixed: tree-sitter now excludes `target`, `build`, `generated-*`, `src/test`; SCIP already did. `namesrv` witness is now `DefaultRequestProcessor.java`. |
| Entry points truncated (30 of 66) and dominated by `example` | Fixed: all 219 `main` methods are emitted. Production entries (23) are separated from example entries (196); containers report both. |
| `unknowns_count` inconsistent with the unknowns list | Fixed: HLD coverage now reports 8 and the list has 8 entries; `unknowns.json` is emitted. |
| HLD witnesses cover only ~4% of files | Documented explicitly: `hld_witness_files=67`, ratio 4.3%, note that witnesses are a capped sample while the source model has per-entity/edge evidence. |
| Edge counts have no aggregation rule | Fixed: `edge_rule` documents the sum of `occurrence_count`, same-module exclusion, one row per ordered pair, `witness_count`, and a capped evidence sample. |
| Maven modules conflated with C4 containers | Mitigated: each container carries `responsibility`, `deployable`, `deployable_evidence`, `production`, and entry-point counts. Deployable status is explicit, not assumed. |
| `system.name` was an absolute local path; no system evidence | Fixed: name is the repository basename; system evidence cites `pom.xml` as `repository_metadata`. |
| Unreconciled entities (37,746 vs 39,101) | Explained: `excluded_file_package_entities=1,347` (file/package entities are not containers). |
| Missing `outline.json`, `unknowns.json`, `hld.md` | Fixed: all three are generated under `artifacts/hld/`. |
| `filter` witness may be parser-generated | Witness selection now prefers main-source files and records `witness_path` + `witness_quality`; parser/generated witnesses are flagged. |

## LLD review — dispositions

| Finding | Disposition |
|---|---|
| 23 of 40 classes came from `target/generated-test-sources` | Fixed by the same source filter; `namesrv` now has 34 classes, all main-source. |
| 45 phantom methods named `call` | Fixed: the SCIP adapter takes the method name from the tree-sitter scope when it disagrees with `display_name`; zero `call` names remain. |
| `NamesrvStartup` absent from the type model | Present. The bootstrap is surfaced through the `NamesrvStartup.start` flow (33 steps); `main` is listed as an untraced surface because its call edge is unresolved. |
| Flow steps cited the callee declaration, not the call site | Fixed: every step beyond depth 0 carries `call_site` evidence from the call edge and a `caller` ID. |
| Registration/lookup/heartbeat existed but were untraced | Fixed: entry selection is diversified and preferred NameServer operations are seeded; flows now include `registerBroker`, `brokerHeartbeat`, and `getRouteInfoByTopic`. |
| Coverage claimed 598 edges while only 500 were serialized | Fixed: coverage now reports `edges_total=563` and `edges_serialized=500`. |
| States, seams, invariants missing | Made explicit: `states`, `seams`, and `invariants` are emitted; `namesrv` has no enums/interfaces in this slice, and unknowns record the gap. |
| Duplicate flow names | Flow entries now carry `class` and `entry` IDs; same-named flows are distinct overloads/classes. |

## Remaining gaps (not fixed)

- No golden labels: overlap metrics are not accuracy.
- No runtime traces; dynamic dispatch/DI flows can be incomplete.
- No data-store or external-system extraction in this slice.
- `namesrv` has no enums/interfaces, so its state/seam sections are empty by evidence, not by omission.
- COBOL, SQL/PL-SQL, React/TypeScript, and C# are out of scope for the Java slice.
- HLD witnesses are samples; a maintainer must still sign off boundaries.

## Verdict

The deterministic baseline is now internally consistent and auditable enough to review with a
maintainer. It is **not** safe to freeze: boundaries, data topology, and runtime flows still
need human confirmation and golden-repo measurement.
