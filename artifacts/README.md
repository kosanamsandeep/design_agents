# Published artifacts — RocketMQ vertical slice

Commit: `efa1be59d6fc747ad220f036c86030f05f0419f9` (`rocketmq-all-5.5.1`).
Tool versions: scip-java 0.13.2, tree-sitter 0.25.2, tree-sitter-java 0.23.5,
evidence schema 1.0.0.

## Browsable, uncompressed

| Path | Contents |
|---|---|
| `hld/c4.model.json` | 16 containers, 40 aggregated edges, entry points, unknowns |
| `hld/outline.json` | Container responsibilities, deployable flags, evidence |
| `hld/unknowns.json` | Open questions and owners |
| `hld/hld.md` | Human-readable HLD baseline |
| `hld/hld.mmd` | Mermaid source |
| `lld/namesrv.lld.json` | 34 classes, 10 flows, states/seams/invariants, call-site evidence |
| `lld/broker.lld.json`, `lld/remoting.lld.json` | Additional context slices |
| `lld/*.mmd`, `*.unknowns.json`, `*.seams.json` | Diagrams and explicit gaps |
| `manifest.json` | Counts, versions, overlap, coverage |

## Large, compressed

| File | Uncompressed | Decompress |
|---|---:|---|
| `published/rocketmq.scip.gz` | 86 MB | `gunzip -k published/rocketmq.scip.gz` |
| `published/evidence.scip.json.gz` | 180 MB | `gunzip -k published/evidence.scip.json.gz` |
| `published/evidence.treesitter.json.gz` | 87 MB | `gunzip -k published/evidence.treesitter.json.gz` |
| `published/code.graph.json.gz` | 235 MB | `gunzip -k published/code.graph.json.gz` |

`published/SHA256SUMS` is the integrity manifest.

The compressed files are the raw evidence and merged graph. The small HLD/LLD JSON is
directly browsable and is what the status page and agents consume.

## Reproduce

```bash
./scripts/index_rocketmq.sh
./scripts/run_rocketmq.sh
```

The test source snapshot is vendored at `testdata/rocketmq` with `.lens-commit` recording the
pinned SHA; build outputs are excluded. The Maven build and SCIP index are reproducible from
that snapshot.
