# Installations — Legacy Lens Java vertical slice

Everything needed to reproduce the first end-to-end run on an open-source Java repository.
The environment is WSL2 Ubuntu; paths are user-local, no system packages were required.

**Test repository:** [`apache/rocketmq`](https://github.com/apache/rocketmq)
**Tag:** `rocketmq-all-5.5.1`
**Commit:** `efa1be59d6fc747ad220f036c86030f05f0419f9`
**Size:** ~39 MB, 2,254 Java files in the checkout; 2,265 SCIP documents after the Maven build;
1,550 main-source documents after the adapter filters
**Licence:** Apache-2.0
**Frozen:** 27 Oct 2026

## Versions

| Component | Version | Location | Purpose | Licence |
|---|---|---|---|---|
| OpenJDK (Temurin) | 21.0.12+8 | `/home/sande/tools/jdk-21.0.12+8` | JVM for Maven and scip-java | GPLv2+CE |
| Apache Maven | 3.9.16 | `/home/sande/tools/apache-maven-3.9.16` | RocketMQ build | Apache-2.0 |
| Python | 3.12.3 | system | adapters and validation | PSF |
| tree-sitter (Python) | 0.25.2 | `.venv` | Java parsing | MIT |
| tree-sitter-java | 0.23.5 | `.venv` | Java grammar | MIT |
| jsonschema | 4.26.0 | `.venv` | schema validation | MIT |
| protobuf | 7.36.2 | `.venv` | SCIP decode | BSD-3-Clause |
| grpcio-tools | 1.85.0 | `.venv` | `protoc` for SCIP | Apache-2.0 |
| scip-java | v0.13.2 binary (reports `0.0.0-SNAPSHOT`) | `~/.local/bin/scip-java` | Java SCIP index | Apache-2.0 |
| SCIP proto | `sourcegraph/scip` main (14 messages) | `legacy_lens/proto/scip.proto` | protobuf schema | Apache-2.0 |

Not installed system-wide: `jq`, `protoc`, `tree-sitter` CLI, Gradle, Coursier. The Python
`grpcio-tools` package supplies `protoc`; the tree-sitter Python bindings are used directly.

## Setup commands

### 1. Java and Maven

Already present on this machine:

```bash
export JAVA_HOME=/home/sande/tools/jdk-21.0.12+8
export PATH="$JAVA_HOME/bin:/home/sande/tools/apache-maven-3.9.16/bin:$PATH"
java -version    # 21.0.12
mvn -version     # 3.9.16
```

### 2. Python virtual environment

```bash
cd /home/sande/workspace/design_agents
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install tree-sitter tree-sitter-java jsonschema protobuf grpcio-tools
```

### 3. SCIP protobuf bindings

```bash
curl -fL -o legacy_lens/proto/scip.proto \
  https://raw.githubusercontent.com/sourcegraph/scip/main/scip.proto
.venv/bin/python -m grpc_tools.protoc \
  -I legacy_lens/proto --python_out=legacy_lens/proto legacy_lens/proto/scip.proto
```

### 4. scip-java

The binary release is used because the Coursier default channel does not carry `scip-java`:

```bash
curl -fL -o ~/.local/bin/scip-java \
  https://github.com/scip-code/scip-java/releases/download/v0.13.2/scip-java-v0.13.2
chmod +x ~/.local/bin/scip-java
scip-java --version
```

### 5. Test repository

```bash
git clone --depth 1 --branch rocketmq-all-5.5.1 \
  https://github.com/apache/rocketmq.git testdata/rocketmq
cd testdata/rocketmq
git rev-parse HEAD   # efa1be59d6fc747ad220f036c86030f05f0419f9
```

### 6. Generate the SCIP index

RocketMQ contains both Maven and Bazel files, so the build tool must be explicit:

```bash
cd testdata/rocketmq
JAVA_HOME=/home/sande/tools/jdk-21.0.12+8 \
PATH="/home/sande/tools/jdk-21.0.12+8/bin:/home/sande/tools/apache-maven-3.9.16/bin:$PATH" \
/home/sande/.local/bin/scip-java index \
  --build-tool=maven \
  --output /home/sande/workspace/design_agents/artifacts/rocketmq.scip
```

## Notes

- `tree-sitter` is pinned to **0.25.2**. Version 0.26.0 segfaulted during garbage collection when
  parsing many Java files with `tree-sitter-java` 0.23.5; 0.25.2 parses the full repository
  cleanly. Record any future version change here and re-run the adapters.
- The first Maven run downloads dependencies into `~/.m2`; subsequent runs are faster.
- `scip-java` lives in `~/.local/bin`; ensure that directory is on `PATH` for the index script.
- The project is indexed at the frozen commit and tag above. Re-running against `develop` will
  produce different evidence.
- All tools are run locally; no source leaves the machine during indexing.
- GPL/LGPL tools are not part of this Java slice. If added later under internal-only policy,
  run them unmodified and record the policy decision here.
- Licences above are the top-level project licences. The SBOM/intake gate still applies to
  transitive dependencies.


## Run the vertical slice

```bash
./scripts/index_rocketmq.sh    # Maven build + SCIP index (one-time / on commit change)
./scripts/run_rocketmq.sh      # SCIP + tree-sitter -> merge -> HLD -> LLD
```

Or via the CLI:

```bash
.venv/bin/python -m legacy_lens.cli run \
  --repo testdata/rocketmq \
  --index artifacts/rocketmq.scip \
  --out-dir artifacts \
  --modules namesrv,broker,remoting
```

Outputs:

| Artifact | Meaning |
|---|---|
| `artifacts/evidence.scip.json` | SCIP-derived evidence (internal, main-source only) |
| `artifacts/evidence.treesitter.json` | tree-sitter evidence (syntax, imports, calls, routes) |
| `artifacts/code.graph.json` | merged evidence model (validated) |
| `artifacts/hld/c4.model.json` | deterministic HLD baseline |
| `artifacts/hld/hld.mmd` | Mermaid rendering of the HLD |
| `artifacts/lld/<module>.lld.json` | per-context LLD baseline |
| `artifacts/manifest.json` | counts, versions, overlap, coverage |

First-slice counts: 34,010 SCIP entities / 86,517 edges; 31,040 tree-sitter entities / 33,574
edges; 38,789 merged entities / 109,647 edges; 16 containers; 40 HLD edges; `namesrv` LLD
34 classes / 10 flows. HLD witnesses cover 67 files (4.3%) and are samples, not exhaustive.
See `README.md`, `docs/run-2026-10-27-rocketmq.md`, and `docs/agent-review-outcomes.md`.
