# HLD baseline

System: `rocketmq`  
Commit: `efa1be59d6fc747ad220f036c86030f05f0419f9`  
Source model: 38789 entities, 109647 edges  
HLD witnesses: 67 files (4.33% of analyzed files) — samples, not exhaustive coverage.

## Containers

| Container | Classes | Methods | Prod. entry | Example entry | Deployable | Evidence |
|---|---:|---:|---:|---:|---|---|
| broker | 890 | 3240 | 1 | 0 | True | `broker/src/main/java/org/apache/rocketmq/broker/BrokerController.java` |
| proxy | 503 | 2483 | 5 | 0 | True | `proxy/src/main/java/org/apache/rocketmq/proxy/service/metadata/ClusterMetadataService.java` |
| remoting | 398 | 3911 | 0 | 0 | False | `remoting/src/main/java/org/apache/rocketmq/remoting/netty/NettyRemotingClient.java` |
| store | 341 | 4280 | 0 | 0 | False | `store/src/main/java/org/apache/rocketmq/store/rocksdb/NativeCqCompactionFilter.java` |
| client | 312 | 3313 | 0 | 0 | False | `client/src/main/java/org/apache/rocketmq/acl/common/AclClientRPCHook.java` |
| common | 285 | 2492 | 2 | 0 | True | `common/src/main/java/org/apache/rocketmq/common/AbortProcessException.java` |
| tools | 242 | 1920 | 10 | 0 | True | `tools/src/main/java/org/apache/rocketmq/tools/command/message/QueryMsgByIdSubCommand.java` |
| auth | 220 | 769 | 0 | 0 | False | `auth/src/main/java/org/apache/rocketmq/auth/authentication/AuthenticationEvaluator.java` |
| controller | 166 | 611 | 1 | 0 | True | `controller/src/main/java/org/apache/rocketmq/controller/BrokerHousekeepingService.java` |
| tieredstore | 108 | 826 | 0 | 0 | False | `tieredstore/src/main/java/org/apache/rocketmq/tieredstore/index/IndexStoreFile.java` |
| example | 98 | 456 | 0 | 196 | False | `example/src/main/java/org/apache/rocketmq/example/batch/SimpleBatchProducer.java` |
| openmessaging | 53 | 279 | 0 | 0 | False | `openmessaging/src/main/java/io/openmessaging/rocketmq/domain/BytesMessageImpl.java` |
| filter | 36 | 488 | 0 | 0 | False | `filter/src/main/java/org/apache/rocketmq/filter/expression/UnaryExpression.java` |
| namesrv | 34 | 226 | 1 | 0 | True | `namesrv/src/main/java/org/apache/rocketmq/namesrv/processor/DefaultRequestProcessor.java` |
| container | 12 | 159 | 3 | 0 | True | `container/src/main/java/org/apache/rocketmq/container/BrokerContainer.java` |
| srvutil | 6 | 27 | 0 | 0 | False | `srvutil/src/main/java/org/apache/rocketmq/srvutil/ShutdownHookThread.java` |

## Top cross-module edges

| From | To | Count | Witnesses |
|---|---|---:|---:|
| broker | remoting | 7840 | 4234 |
| broker | common | 6667 | 4052 |
| client | remoting | 5214 | 3682 |
| client | common | 3668 | 2216 |
| tools | client | 3488 | 1651 |
| store | common | 3335 | 2050 |
| broker | store | 2884 | 1746 |
| tools | remoting | 2606 | 1878 |
| broker | client | 2288 | 825 |
| proxy | remoting | 1803 | 1236 |
| proxy | client | 1586 | 881 |
| proxy | common | 1472 | 1028 |
| remoting | common | 1261 | 1014 |
| store | client | 1151 | 583 |
| example | client | 1093 | 740 |
| remoting | client | 1090 | 663 |
| namesrv | remoting | 1051 | 674 |
| tools | common | 924 | 589 |
| controller | remoting | 897 | 595 |
| common | client | 883 | 471 |

**Edge rule:** count = sum of occurrence_count for calls/uses/extends/implements edges between different modules; same-module edges are excluded; one row per ordered module pair; witness_count is the number of merged edges that contributed; evidence is a capped sample (up to 3).

## Unknowns

- **medium** — SCIP symbol kinds not mapped to the evidence model: TypeParameter (120), UnspecifiedKind (6940), Variable (27073)
- **low** — 703 test-source Java files were excluded from architecture evidence.
- **medium** — tree-sitter reported parse errors in filter/src/main/java/org/apache/rocketmq/filter/parser/SelectorParser.java; syntax evidence may be incomplete.
- **low** — 12 generated/build-output Java files were excluded from architecture evidence.
- **medium** — 54023 call/new sites could not be resolved by unique name and were not emitted.
- **medium** — No data-store/config evidence was extracted; confirm whether the system uses external stores or only local files.
- **medium** — No external systems or actors were identified; confirm upstream/downstream integrations.
- **low** — 196 example/test main methods are excluded from production entry-point selection.

This is a generated baseline, not a signed-off architecture. See `outline.json` and `c4.model.json`.
