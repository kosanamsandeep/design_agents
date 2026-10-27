"""Deterministic HLD/LLD baseline from a validated evidence model.

The baseline is the non-LLM starting point the synthesis agents refine. It
aggregates evidence by source module/container, preserves evidence pointers, and
never invents relationships. Counts, rules, and truncation are written into the
artifacts so a reviewer can audit them.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CONTAINER_PREFIX = "container:"
EDGE_KINDS = {"calls", "uses", "extends", "implements"}
MAX_HLD_EDGES = 40
MAX_EVIDENCE_PER_HLD_EDGE = 3
MAX_LLD_CLASSES = 60
MAX_LLD_EDGES = 500

ENTRY_NAMES = {
    "main", "registerBroker", "brokerHeartbeat", "getRouteInfoByTopic",
    "processRequest", "initialize", "start", "run", "process", "handle", "execute",
}

RESPONSIBILITIES = {
    "broker": "Message ingest, dispatch, subscription, and broker lifecycle.",
    "namesrv": "Broker registration and topic route metadata.",
    "proxy": "Client-facing remoting/gRPC front door.",
    "controller": "HA election and replication control.",
    "container": "Hosts multiple brokers in one process.",
    "store": "Local commitlog/consume-queue message storage.",
    "tieredstore": "Tiered/remote storage extension.",
    "remoting": "Netty RPC, protocol, and transport.",
    "client": "Producer/consumer/admin client SDK.",
    "tools": "CLI and admin operations.",
    "auth": "Authentication and authorization evaluation.",
    "common": "Shared utilities and common APIs.",
    "srvutil": "Shared service utilities.",
    "filter": "Message filter SPI and implementations.",
    "openmessaging": "OpenMessaging API compatibility.",
    "logging": "Logging integration.",
    "distribution": "Packaging and distribution.",
}


def load(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def module_of(path: str | None) -> str:
    if not path:
        return "unknown"
    first = path.strip("/").split("/", 1)[0]
    return first or "unknown"


def _evidence(entity: dict, limit: int = 2) -> list[dict]:
    return entity.get("evidence", [])[:limit]


def _mermaid_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name) or "unknown"


def _system_evidence(model: dict) -> list[dict]:
    root = model.get("repository", {}).get("root", "")
    commit = model.get("repository", {}).get("commit")
    if not root or not commit:
        return []
    for name in ("pom.xml", "build.gradle", "README.md"):
        if (Path(root) / name).exists():
            return [{
                "tool": "repo-inspector",
                "tool_version": "0.1",
                "type": "repository_metadata",
                "path": name,
                "commit": commit,
            }]
    return []


def summarize_hld(model: dict, top_edges: int = MAX_HLD_EDGES) -> dict:
    entities = model.get("entities", [])
    edges = model.get("edges", [])
    modules: dict[str, dict] = {}
    entity_module: dict[str, str] = {}
    file_package_entities = 0

    for ent in entities:
        if ent.get("kind") in ("file", "package"):
            file_package_entities += 1
            continue
        mod = module_of(ent.get("path"))
        entity_module[ent["id"]] = mod
        info = modules.setdefault(mod, {
            "classes": 0, "interfaces": 0, "enums": 0,
            "methods": 0, "fields": 0, "files": set(), "evidence": [],
        })
        kind = ent.get("kind")
        if kind == "class":
            info["classes"] += 1
        elif kind in ("interface", "enum", "method", "field"):
            info[kind + "s"] += 1
        if ent.get("path"):
            info["files"].add(ent["path"])
        if ent.get("evidence"):
            path = (ent.get("path") or "").lower()
            quality = "generated_or_parser" if any(
                k in path for k in ("generated", "tokenmgr", "_jmh", "/parser/")
            ) else "main_source"
            if "witness_path" not in info or (
                quality == "main_source" and info.get("witness_quality") != "main_source"
            ):
                info["evidence"] = _evidence(ent)
                info["witness_path"] = ent.get("path")
                info["witness_quality"] = quality

    all_entries = []
    entry_by_module: Counter = Counter()
    example_by_module: Counter = Counter()
    for ent in entities:
        if ent.get("kind") == "method" and ent.get("name") == "main":
            mod = entity_module.get(ent["id"], "unknown")
            is_example = mod in ("example", "test")
            if is_example:
                example_by_module[mod] += 1
            else:
                entry_by_module[mod] += 1
            all_entries.append({
                "id": ent["id"],
                "module": mod,
                "path": ent.get("path"),
                "is_example": is_example,
                "evidence": _evidence(ent, 1),
            })
    entry_points = [e for e in all_entries if not e["is_example"]]
    example_entry_points = [e for e in all_entries if e["is_example"]]

    containers = []
    for mod, info in sorted(modules.items()):
        if mod == "unknown":
            continue
        entries = entry_by_module.get(mod, 0)
        containers.append({
            "id": f"{CONTAINER_PREFIX}{mod}",
            "name": mod,
            "module": mod,
            "responsibility": RESPONSIBILITIES.get(mod, f"{mod} module."),
            "classes": info["classes"],
            "interfaces": info["interfaces"],
            "enums": info["enums"],
            "methods": info["methods"],
            "fields": info["fields"],
            "files": len(info["files"]),
            "entry_points": entries,
            "example_entry_points": example_by_module.get(mod, 0),
            "deployable": entries > 0,
            "deployable_evidence": "main method present" if entries else "no main method found",
            "production": mod not in ("example", "test"),
            "confidence": "inferred",
            "witness_path": info.get("witness_path"),
            "witness_quality": info.get("witness_quality", "unknown"),
            "evidence": info["evidence"],
        })

    counts: Counter = Counter()
    witness_counts: Counter = Counter()
    edge_evidence: dict[tuple, list] = defaultdict(list)
    cross_module_edges = 0
    same_module_edges = 0
    for edge in edges:
        if edge.get("kind") not in EDGE_KINDS:
            continue
        src = entity_module.get(edge.get("from"))
        dst = entity_module.get(edge.get("to"))
        if not src or not dst or "unknown" in (src, dst):
            continue
        if src == dst:
            same_module_edges += 1
            continue
        cross_module_edges += 1
        key = (src, dst)
        counts[key] += edge.get("attributes", {}).get("occurrence_count", 1)
        witness_counts[key] += 1
        for ev in edge.get("evidence", [])[:1]:
            if len(edge_evidence[key]) < MAX_EVIDENCE_PER_HLD_EDGE:
                edge_evidence[key].append(ev)

    hld_edges = []
    for (src, dst), count in counts.most_common(top_edges):
        hld_edges.append({
            "id": f"edge:{CONTAINER_PREFIX}{src}|depends_on|{CONTAINER_PREFIX}{dst}",
            "from": f"{CONTAINER_PREFIX}{src}",
            "to": f"{CONTAINER_PREFIX}{dst}",
            "kind": "depends_on",
            "count": count,
            "witness_count": witness_counts[(src, dst)],
            "confidence": "inferred",
            "evidence": edge_evidence[(src, dst)],
        })

    unknowns = []
    seen_unknowns = set()
    for unknown in model.get("unknowns", []):
        if unknown.get("id") not in seen_unknowns:
            unknowns.append(unknown)
            seen_unknowns.add(unknown.get("id"))
    no_stores = not any(e.get("kind") in ("datastore", "table", "queue", "topic")
                        for e in entities)
    if no_stores:
        unknowns.append({
            "id": "unknown:data-stores",
            "question": "No data-store/config evidence was extracted; confirm whether the system uses external stores or only local files.",
            "impact": "medium",
            "owner": "repo-owner",
        })
    if not any(ent.get("kind") == "external_system" for ent in entities):
        unknowns.append({
            "id": "unknown:external-systems",
            "question": "No external systems or actors were identified; confirm upstream/downstream integrations.",
            "impact": "medium",
            "owner": "repo-owner",
        })
    if example_entry_points:
        unknowns.append({
            "id": "unknown:example-entry-points",
            "question": f"{len(example_entry_points)} example/test main methods are excluded from production entry-point selection.",
            "impact": "low",
            "owner": "repo-owner",
        })

    coverage = dict(model.get("coverage", {}))
    coverage["unknowns_count"] = len(unknowns)
    witness_paths = {ev.get("path") for c in containers for ev in c["evidence"] if ev.get("path")}
    witness_paths |= {ev.get("path") for e in hld_edges for ev in e["evidence"] if ev.get("path")}
    analyzed = max(1, coverage.get("files_analyzed", 0))
    coverage["hld_witness_files"] = len(witness_paths)
    coverage["hld_witness_ratio"] = round(len(witness_paths) / analyzed, 4)
    coverage["hld_witness_note"] = (
        "HLD witnesses are a capped sample per container/module pair; the source model "
        "has evidence for every entity and edge."
    )
    coverage["entry_points_production"] = len(entry_points)
    coverage["entry_points_example"] = len(example_entry_points)
    root = model.get("repository", {}).get("root", "")
    return {
        "schema": "c4/v1",
        "system": {
            "id": "system:legacy-lens",
            "name": Path(root).name if root else "repository",
            "commit": model.get("repository", {}).get("commit"),
            "evidence": _system_evidence(model),
        },
        "containers": containers,
        "edges": hld_edges,
        "entry_points": entry_points,
        "example_entry_points": example_entry_points,
        "unknowns": unknowns,
        "coverage": coverage,
        "edge_rule": (
            "count = sum of occurrence_count for calls/uses/extends/implements edges "
            "between different modules; same-module edges are excluded; one row per "
            "ordered module pair; witness_count is the number of merged edges that "
            "contributed; evidence is a capped sample (up to 3)."
        ),
        "source_model": {
            "entities": len(entities),
            "edges": len(edges),
            "excluded_file_package_entities": file_package_entities,
            "cross_module_edges_counted": cross_module_edges,
            "same_module_edges_excluded": same_module_edges,
        },
    }


def hld_mermaid(hld: dict, max_edges: int = 30) -> str:
    lines = ["flowchart LR"]
    for c in hld["containers"]:
        cid = _mermaid_id(c["module"])
        role = "deployable" if c["deployable"] else "library/module"
        label = (f'{c["module"]}<br/>{c["classes"]} classes · '
                 f'{c["methods"]} methods<br/>{role} · {c["entry_points"]} entry')
        lines.append(f'    {cid}["{label}"]')
    for e in hld["edges"][:max_edges]:
        src = _mermaid_id(e["from"].split(":", 1)[1])
        dst = _mermaid_id(e["to"].split(":", 1)[1])
        lines.append(f'    {src} -->|"{e["count"]} / {e["witness_count"]}w"| {dst}')
    return "\n".join(lines) + "\n"


def lld_for_module(model: dict, module: str, max_classes: int = MAX_LLD_CLASSES,
                   max_flows: int = 10, max_depth: int = 4) -> dict:
    entities = [e for e in model.get("entities", [])
                if module_of(e.get("path")) == module]
    ids = {e["id"] for e in entities}
    edges = [e for e in model.get("edges", [])
             if e.get("from") in ids and e.get("to") in ids
             and e.get("kind") in ("calls", "uses", "extends", "implements")]
    call_edges = [e for e in edges if e.get("kind") == "calls"]

    degree: Counter = Counter()
    for e in edges:
        degree[e["from"]] += 1
        degree[e["to"]] += 1
    parent_by_id = {e["id"]: e.get("parent_id") for e in entities}

    classes = []
    for ent in entities:
        if ent.get("kind") not in ("class", "interface", "enum"):
            continue
        methods = [m for m in entities
                   if m.get("kind") == "method" and m.get("parent_id") == ent["id"]]
        fields = [f for f in entities
                  if f.get("kind") == "field" and f.get("parent_id") == ent["id"]]
        classes.append({
            "id": ent["id"],
            "name": ent.get("name"),
            "kind": ent.get("kind"),
            "path": ent.get("path"),
            "degree": degree.get(ent["id"], 0),
            "methods": [
                {"id": m["id"], "name": m.get("name"),
                 "parameters": m.get("attributes", {}).get("parameters"),
                 "evidence": _evidence(m, 1)}
                for m in methods[:30]
            ],
            "fields": [
                {"id": f["id"], "name": f.get("name"),
                 "evidence": _evidence(f, 1)}
                for f in fields[:20]
            ],
            "evidence": _evidence(ent),
        })
    classes.sort(key=lambda c: (-c["degree"], c["name"] or ""))
    classes = classes[:max_classes]

    adjacency: dict[str, list[str]] = defaultdict(list)
    edge_lookup: dict[tuple, dict] = {}
    for e in call_edges:
        adjacency[e["from"]].append(e["to"])
        edge_lookup[(e["from"], e["to"])] = e

    preferred_order = ["registerBroker", "brokerHeartbeat", "getRouteInfoByTopic",
                       "unRegisterBroker", "processRequest", "initialize", "start",
                       "main", "run", "process", "handle", "execute"]
    preferred_rank = {name: i for i, name in enumerate(preferred_order)}
    raw_entries = [e for e in entities
                   if e.get("kind") == "method" and e.get("name") in ENTRY_NAMES]
    raw_entries.sort(key=lambda e: (preferred_rank.get(e.get("name"), 99),
                                    -degree.get(e["id"], 0)))
    entries = []
    seen_entries = set()
    for e in raw_entries:
        key = (parent_by_id.get(e["id"]), e.get("name"))
        if key in seen_entries:
            continue
        seen_entries.add(key)
        entries.append(e)
    if not entries:
        entries = sorted([e for e in entities if e.get("kind") == "method"],
                         key=lambda e: -degree.get(e["id"], 0))[:5]

    flows = []
    for entry in entries[:max_flows]:
        steps = []
        seen = set()
        frontier = [(entry["id"], 0, None)]
        while frontier and len(steps) < 40:
            current, depth, via_edge = frontier.pop(0)
            if current in seen or depth > max_depth:
                continue
            seen.add(current)
            ent = next((e for e in entities if e["id"] == current), None)
            if ent is None:
                continue
            steps.append({
                "id": current,
                "name": ent.get("name"),
                "class": parent_by_id.get(current),
                "depth": depth,
                "evidence": _evidence(ent, 1),
                "call_site": (via_edge or {}).get("evidence", [])[:1],
                "caller": (via_edge or {}).get("from"),
            })
            for nxt in adjacency.get(current, [])[:8]:
                if nxt not in seen:
                    frontier.append((nxt, depth + 1, edge_lookup.get((current, nxt))))
        if len(steps) > 1:
            flows.append({
                "entry": entry["id"],
                "name": entry.get("name"),
                "class": parent_by_id.get(entry["id"]),
                "steps": steps,
            })

    traced_entries = {f["entry"] for f in flows}
    surfaces = [
        {"id": e["id"], "name": e.get("name"), "class": parent_by_id.get(e["id"]),
         "evidence": _evidence(e, 1),
         "note": "entry-point-like operation with no traced outgoing calls"}
        for e in entries if e["id"] not in traced_entries
    ][:10]

    # Include classes referenced by flows even if they fell outside the degree cap.
    included = {c["id"] for c in classes}
    by_id = {e["id"]: e for e in entities}
    for flow in flows:
        for step in flow["steps"]:
            cid = step.get("class")
            if cid and cid not in included and cid in by_id:
                ent = by_id[cid]
                classes.append({
                    "id": cid,
                    "name": ent.get("name"),
                    "kind": ent.get("kind"),
                    "path": ent.get("path"),
                    "degree": degree.get(cid, 0),
                    "from_flow": True,
                    "methods": [],
                    "fields": [],
                    "evidence": _evidence(ent),
                })
                included.add(cid)

    states = [
        {"id": e["id"], "name": e.get("name"), "evidence": _evidence(e, 1),
         "transitions": [], "status": "not_extracted"}
        for e in entities if e.get("kind") == "enum"
    ]
    seams = [
        {"id": e["id"], "name": e.get("name"), "path": e.get("path"),
         "kind": "interface", "evidence": _evidence(e, 1),
         "note": "candidate seam; confirm DI/registration"}
        for e in entities if e.get("kind") == "interface"
    ]

    serialized_edges = edges[:MAX_LLD_EDGES]
    unknowns = [
        {
            "id": f"unknown:lld-{module}-visibility",
            "question": "Method visibility and framework annotations are not fully modelled; confirm public entry points with the maintainer.",
            "impact": "medium",
            "owner": "repo-owner",
        },
        {
            "id": f"unknown:lld-{module}-states",
            "question": "State transitions were not extracted; enums are listed but transitions need maintainer confirmation.",
            "impact": "medium",
            "owner": "repo-owner",
        },
        {
            "id": f"unknown:lld-{module}-invariants",
            "question": "Invariants were not extracted from validation/constraint evidence.",
            "impact": "medium",
            "owner": "repo-owner",
        },
    ]
    if surfaces:
        unknowns.append({
            "id": f"unknown:lld-{module}-untraced-surfaces",
            "question": "Entry-point-like operations without traced outgoing calls: " +
                        ", ".join(s["name"] or s["id"] for s in surfaces) +
                        ". Confirm whether calls are unresolved or the operation is a leaf.",
            "impact": "medium",
            "owner": "repo-owner",
        })
    coverage_unknowns = len(unknowns)
    return {
        "schema": "lld/v1",
        "context": module,
        "commit": model.get("repository", {}).get("commit"),
        "classes": classes,
        "flows": flows,
        "surfaces": surfaces,
        "states": states,
        "seams": seams,
        "invariants": [],
        "edges": [
            {"from": e["from"], "to": e["to"], "kind": e["kind"],
             "confidence": e.get("confidence"),
             "occurrence_count": e.get("attributes", {}).get("occurrence_count", 1),
             "evidence": _evidence(e, 1)}
            for e in serialized_edges
        ],
        "unknowns": unknowns,
        "coverage": {
            "entities": len(entities),
            "edges_total": len(edges),
            "edges_serialized": len(serialized_edges),
            "classes_total": sum(1 for e in entities
                                 if e.get("kind") in ("class", "interface", "enum")),
            "classes_included": len(classes),
            "unknowns_count": coverage_unknowns,
        },
    }


def lld_mermaid(lld: dict, max_classes: int = 12, max_edges: int = 30) -> str:
    lines = ["flowchart LR"]
    ids = {}
    for cls in lld["classes"][:max_classes]:
        cid = _mermaid_id(cls["id"])
        ids[cls["id"]] = cid
        lines.append(f'    {cid}["{cls["name"]}<br/>{cls["degree"]} deg"]')
    shown = 0
    for edge in lld["edges"]:
        src = ids.get(edge["from"])
        dst = ids.get(edge["to"])
        if src and dst and edge["kind"] == "calls" and shown < max_edges:
            lines.append(f'    {src} -->|"{edge["occurrence_count"]}"| {dst}')
            shown += 1
    return "\n".join(lines) + "\n"


def write_hld(model_path: str | Path, out_dir: str | Path) -> dict:
    model = load(model_path)
    hld = summarize_hld(model)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "c4.model.json").write_text(json.dumps(hld, indent=2) + "\n", encoding="utf-8")
    (out / "hld.mmd").write_text(hld_mermaid(hld), encoding="utf-8")
    (out / "unknowns.json").write_text(json.dumps(hld["unknowns"], indent=2) + "\n",
                                       encoding="utf-8")
    outline = {
        "schema": "outline/v1",
        "commit": hld["system"]["commit"],
        "frozen": False,
        "containers": [
            {
                "id": c["id"],
                "name": c["name"],
                "responsibility": c["responsibility"],
                "deployable": c["deployable"],
                "deployable_evidence": c["deployable_evidence"],
                "entry_points": c["entry_points"],
                "classes": c["classes"],
                "witness_path": c.get("witness_path"),
                "witness_quality": c.get("witness_quality"),
                "evidence": c["evidence"],
            }
            for c in hld["containers"]
        ],
        "note": "Generated baseline. A maintainer must sign off boundaries before LLD fan-out.",
    }
    (out / "outline.json").write_text(json.dumps(outline, indent=2) + "\n", encoding="utf-8")
    md = ["# HLD baseline", "",
          f"System: `{hld['system']['name']}`  ",
          f"Commit: `{hld['system']['commit']}`  ",
          f"Source model: {hld['source_model']['entities']} entities, "
          f"{hld['source_model']['edges']} edges  ",
          f"HLD witnesses: {hld['coverage'].get('hld_witness_files')} files "
          f"({hld['coverage'].get('hld_witness_ratio', 0):.2%} of analyzed files) — "
          "samples, not exhaustive coverage.", "",
          "## Containers", "",
          "| Container | Classes | Methods | Prod. entry | Example entry | Deployable | Evidence |",
          "|---|---:|---:|---:|---:|---|---|"]
    for c in sorted(hld["containers"], key=lambda c: -c["classes"]):
        ev = c["evidence"][0]["path"] if c["evidence"] else "—"
        md.append(f"| {c['name']} | {c['classes']} | {c['methods']} | "
                  f"{c['entry_points']} | {c['example_entry_points']} | "
                  f"{c['deployable']} | `{ev}` |")
    md += ["", "## Top cross-module edges", "",
           "| From | To | Count | Witnesses |", "|---|---|---:|---:|"]
    for e in hld["edges"][:20]:
        md.append(f"| {e['from'].split(':')[1]} | {e['to'].split(':')[1]} | "
                  f"{e['count']} | {e['witness_count']} |")
    md += ["", f"**Edge rule:** {hld['edge_rule']}", "",
           "## Unknowns", ""]
    for u in hld["unknowns"]:
        md.append(f"- **{u.get('impact','')}** — {u.get('question','')}")
    md += ["", "This is a generated baseline, not a signed-off architecture. "
           "See `outline.json` and `c4.model.json`.", ""]
    (out / "hld.md").write_text("\n".join(md), encoding="utf-8")
    return hld


def write_lld(model_path: str | Path, module: str, out_dir: str | Path) -> dict:
    model = load(model_path)
    lld = lld_for_module(model, module)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{module}.lld.json").write_text(json.dumps(lld, indent=2) + "\n",
                                            encoding="utf-8")
    (out / f"{module}.mmd").write_text(lld_mermaid(lld), encoding="utf-8")
    (out / f"{module}.unknowns.json").write_text(json.dumps(lld["unknowns"], indent=2) + "\n",
                                                 encoding="utf-8")
    (out / f"{module}.seams.json").write_text(json.dumps(lld["seams"], indent=2) + "\n",
                                              encoding="utf-8")
    return lld
