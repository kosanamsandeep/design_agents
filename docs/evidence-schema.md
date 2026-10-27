# Evidence model v1 — contract

The machine-readable schema is [`evidence-schema.v1.json`](evidence-schema.v1.json) (JSON Schema
2020-12, `schema_version` `1.0.0`). This page is the written contract that JSON Schema cannot
express: stable IDs, canonicalization, evidence types, conflict resolution, referential integrity,
and coverage invariants.

> **Status: draft v1.0.0.** The contract suite (`python3 docs/contract_tests.py`) passes for the
> current fixtures, but v1 is not frozen until the first two adapters run against it on a real
> repository. No adapter may treat the schema as stable before that point.

## 1 · Why this exists

Every tool — SCIP, tree-sitter, Graphify, CodeGraph, CodeBoarding, Joern, an LLM — is an
**adapter** into this model. No tool output is the model, and no tool is truth. The model is the
only thing the HLD/LLD stages consume. That is what makes tools replaceable and the pipeline
auditable.

## 2 · Stable IDs and canonicalization

IDs are deterministic and assigned by the adapter, never by array position or display name.

| Entity type | ID form | Example |
|---|---|---|
| Code entity | `<kind>:<language>:<repo-relative-path>#<qualified-name>` | `method:python:services/billing/service.py#Invoice.issue` |
| File / module | `<kind>:<language>:<repo-relative-path>` | `module:python:services/billing` |
| Route | `route:<method>:<canonical-path>` | `route:post:/invoices/{param}` |
| Tabular store | `table:<datastore>:<schema>.<table>` | `table:postgres:billing.invoice` |
| Queue / topic | `<kind>:<broker>:<name>` | `topic:kafka:order.placed` |
| Deployable unit | `container:<deploy-name>` | `container:billing` |
| External system | `external_system:<canonical-name>` | `external_system:stripe` |
| Edge | `<edge>:<from>\|<kind>\|<to>` (percent-encoded or hashed if long) | `edge:container:orders\|publishes\|topic:kafka:order.placed` |

### Canonicalization rules

Shared fixtures: [`canonicalization-fixtures.json`](canonicalization-fixtures.json). Reference
implementation: [`canonicalize.py`](canonicalize.py). Every adapter must pass the same fixtures.

**Paths**
1. Repo-relative, POSIX `/` separators; reject absolute paths and backslashes.
2. NFC Unicode normalization; preserve case (source paths are case-sensitive in git).
3. Remove leading `./`, collapse duplicate slashes, remove trailing slash except the repository
   root `.`.

**Routes**
1. Lower-case the HTTP method.
2. Strip query string and fragment.
3. Collapse duplicate slashes, ensure a leading `/`, remove trailing `/` except root.
4. Normalize every path parameter to `{param}` regardless of spelling (`{invoice_id}`, `:id`,
   `<id>`). Parameter names belong in `attributes`, not in identity.
5. Preserve path case; routes can be case-sensitive.

**Qualified names**
- Python: `module.Class.method`; Java/Kotlin/Scala: `package.Class#method`; TypeScript/JavaScript:
  `module#exportedName` or `module#Class.method`; Go: `package.Func` or
  `package.Receiver.Method`; C#: `Namespace.Class.Method`.
- Overloaded methods append `@<8-char hash of normalized parameter types>` so overloads do not
  collapse into one identity. Document the normalization in the adapter.
- Generated names (lambdas, anonymous classes, synthetic members) include a hash of the enclosing
  source span and set `attributes.synthetic = true`.

**Renames and moves**
- Create the new ID and add the old ID to `aliases`. Never reuse an old ID for a different entity.
- If a parser cannot determine a stable identity, **do not emit** a guess: record an unknown or a
  conflict and fail closed.

## 3 · Confidence is not correctness

| Value | Meaning | Who may set it |
|---|---|---|
| `extracted` | Directly observed by a parser/indexer at the cited span. | SCIP, tree-sitter, LSP, config/deploy parser |
| `inferred` | Derived by a deterministic rule or a join of extracted facts. | Adapter rule, graph query |
| `hypothesis` | Proposed by an LLM/agent, or unresolved after a conflict. | LLM, critic, unknown |

`extracted` means the claim was observed, not that the architecture is complete. A call edge can be
extracted correctly while dynamic dispatch makes the runtime flow incomplete; an inferred ownership
relationship can be correct. Evaluate these dimensions separately:

1. **Evidence validity** — does the cited source exist at the recorded commit and span?
2. **Claim entailment** — does that source actually support this specific claim?
3. **Structural correctness** — are entity identity, edge endpoints, and relationship types right?
4. **Coverage** — what was analyzed, skipped, or left unknown?
5. **Runtime confirmation** — for critical flows, is static evidence enough, or is tracing needed?

Do not add a more elaborate confidence taxonomy until the pilot shows the three levels are
insufficient.

## 4 · Evidence

Every entity and edge requires at least one evidence item. Each item requires:

| Field | Required | Rule |
|---|---|---|
| `tool` | yes | Adapter/tool identity. |
| `tool_version` | yes | Exact version string. |
| `type` | yes | `source_span`, `config`, `runtime_trace`, `repository_metadata`, or `external`. |
| `path` | yes | Repo-relative POSIX path; no leading `/`, no backslashes. Runtime traces may use `runtime://…`. |
| `commit` | yes | Commit at which the evidence was read. |
| `span` | conditional | Required when `type=source_span`; optional for whole-file config/metadata. |
| `extractor` | no | Sub-component or query name. |
| `snippet_hash` | recommended | Hash of the cited snippet for drift detection. |
| `note` | no | Human-readable context. |

A resolvable `file:line` is necessary but not sufficient: the claim must be entailed by the cited
code, and that is sampled by humans during evaluation. Evidence validity and entailment are
separate metrics.

## 5 · Conflict rule

Every competing claim carries a stable `claim_id` (pattern `claim:…`). A conflict records all
claims and a resolution:

```json
{
  "id": "conflict:invoice-owner",
  "subject": "table:postgres:billing.invoice",
  "claims": [
    {
      "claim_id": "claim:owner-billing",
      "tool": "codeboarding",
      "tool_version": "0.8.0",
      "value": { "owner": "billing" },
      "confidence": "inferred",
      "evidence": [ { "tool": "codeboarding", "tool_version": "0.8.0",
                      "type": "config", "path": "deploy/k8s/billing.yaml",
                      "commit": "9f3c2a1" } ]
    },
    {
      "claim_id": "claim:owner-orders",
      "tool": "codegraph",
      "tool_version": "1.4.0",
      "value": { "owner": "orders" },
      "confidence": "extracted",
      "evidence": [ { "tool": "codegraph", "tool_version": "1.4.0",
                      "type": "source_span", "path": "services/orders/repo.py",
                      "commit": "9f3c2a1", "span": { "start_line": 50, "end_line": 58 } } ]
    }
  ],
  "resolution": {
    "status": "unresolved",
    "chosen": null,
    "reason": "Two extracted claims disagree; the billing owner must confirm the data model."
  }
}
```

Resolution requirements (enforced by the schema and the semantic validator):

| State | Required | Forbidden |
|---|---|---|
| `unresolved` | `reason`; `chosen: null` | a non-null `chosen` |
| `resolved` | `chosen` (a `claim_id` from `claims`), `by`, `reason` | a `chosen` that is not one of the claims |
| `by: rule` | `rule` matching `<name>@v<number>` (e.g. `static-precedence@v1`) | an unversioned rule name |
| `by: human` | `reviewer` (person or review-record ID) | a missing reviewer |

`chosen` is always a **claim ID**, never a serialized value or tool name.

### Resolution precedence

1. **Static structure:** compiler/type-resolved index (SCIP) > language server (LSP) > AST /
   tree-sitter > manifest/config inference.
2. **Runtime behaviour:** a runtime trace beats static inference for *what actually happened*;
   static structure still wins for *what can happen*. Record which question is being answered in
   `resolution.reason`.
3. **Epistemic status:** `extracted` > `inferred` > `hypothesis`, but see §3 — extracted evidence
   can still be incomplete.
4. **Human resolution wins** over a default rule when recorded with `by: human`, a `reviewer`, and
   a reason.
5. **Never silently overwrite.** Merge identical `from`/`to`/`kind` claims by unioning evidence; if
   attributes disagree, create a conflict. Deletion/absence is a claim too.
6. **LLM claims start as `hypothesis`.** Promote to `inferred` only with corroborating extracted
   evidence or a named rule; record the promotion.

## 6 · Referential integrity and coverage invariants

JSON Schema validates fields; [`validate_evidence.py`](validate_evidence.py) validates semantics:

- Entity IDs and edge IDs are unique.
- Every edge `from` and `to` points to an existing entity.
- Every non-null `parent_id` resolves to an entity.
- Every conflict `subject` and non-null unknown `subject` resolves to an entity or edge.
- Every resolved `chosen` references one of that conflict's `claim_id` values.
- Evidence paths are repo-relative: no leading `/`, no leading `./`, no backslashes.
- `files_analyzed + files_skipped == files_total` (the categories are mutually exclusive and
  exhaustive).
- `coverage.unknowns_count == len(unknowns)`.

Run it on any instance:

```bash
python3 docs/validate_evidence.py docs/fixtures/valid/minimal.json
python3 docs/validate_evidence.py --all docs/fixtures/valid
```

## 7 · Versioning and freezing v1

- `schema_version` follows semver; breaking changes bump the major version and require a migration
  note.
- `repository.tool_versions` records exact tool versions; every evidence item records its own
  `tool_version`.
- Skills, adapters, recipes, and eval datasets are versioned independently of the schema.
- The schema is **not frozen** until `docs/contract_tests.py` passes and two independent adapters
  (SCIP + tree-sitter) emit consistent, auditable records for the same small repository.
- Contract changes require a new fixture in both `fixtures/valid` and `fixtures/invalid`, with the
  expected rule named in `contract_tests.py`.

## 8 · Example fixtures

- [`fixtures/valid/minimal.json`](fixtures/valid/minimal.json) — canonical valid instance.
- [`fixtures/valid/resolved-human.json`](fixtures/valid/resolved-human.json) — human resolution with
  reviewer.
- [`fixtures/valid/resolved-rule.json`](fixtures/valid/resolved-rule.json) — versioned rule
  resolution.
- [`fixtures/invalid/`](fixtures/invalid/) — one fixture per rule violation; the contract suite
  asserts the expected failure.

## 9 · Adapters and contract tests

An adapter is a pure function from a tool's native output to this model. It must:

1. Assign canonical IDs using the rules in §2 and pass the shared fixtures.
2. Preserve `file:line`, commit, tool version, and evidence type.
3. Fail closed: emit nothing for a claim it cannot represent faithfully; record an unknown instead.
4. Never invent claims; mark LLM output `hypothesis` until corroborated.
5. Declare its tool name and exact version.

The contract suite compares adapters, not tools, on the same golden repositories and schema
version:

```bash
python3 docs/contract_tests.py
```

Current result: 3 valid fixtures, 14 invalid fixtures, and 14 canonicalization cases pass.
