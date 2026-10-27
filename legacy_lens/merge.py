"""Deterministic merge of evidence models from multiple adapters.

Equivalent entities and edges are unioned by stable ID/key; evidence is merged,
confidence keeps the strongest epistemic status, and disagreements are retained
as conflict records rather than silently overwritten.
"""

from __future__ import annotations

import copy
import json
from collections import OrderedDict

from .canonical import short_hash

CONFIDENCE_RANK = {"hypothesis": 0, "inferred": 1, "extracted": 2}


def _ev_key(ev: dict) -> tuple:
    s = ev.get("span") or {}
    return (ev.get("tool"), ev.get("path"), s.get("start_line"), s.get("end_line"), ev.get("type"))


def _merge_evidence(a: list[dict], b: list[dict], limit: int = 10) -> list[dict]:
    out = list(a)
    seen = {_ev_key(e) for e in out}
    for ev in b:
        k = _ev_key(ev)
        if k not in seen:
            out.append(ev)
            seen.add(k)
    return out[:limit]


def _conflict_id(subject: str, reason: str) -> str:
    return f"conflict:{short_hash(subject + '|' + reason)}"


def _claim(tool: str, value: dict, confidence: str, evidence_items: list[dict]) -> dict:
    return {
        "claim_id": f"claim:{short_hash(tool + '|' + json.dumps(value, sort_keys=True))}",
        "tool": tool or "unknown",
        "value": value,
        "confidence": confidence,
        "evidence": evidence_items,
    }


def merge_instances(instances: list[dict]) -> dict:
    if not instances:
        raise ValueError("no instances to merge")
    commits = {i.get("repository", {}).get("commit") for i in instances}
    if len(commits) > 1:
        raise ValueError(f"refusing to merge different commits: {commits}")

    base = copy.deepcopy(instances[0])
    entities: OrderedDict[str, dict] = OrderedDict(
        (e["id"], e) for e in base.get("entities", [])
    )
    edges: OrderedDict[tuple, dict] = OrderedDict(
        ((e["from"], e["to"], e["kind"]), e) for e in base.get("edges", [])
    )
    conflicts: OrderedDict[str, dict] = OrderedDict(
        (c["id"], c) for c in base.get("conflicts", [])
    )
    unknowns: OrderedDict[str, dict] = OrderedDict(
        (u["id"], u) for u in base.get("unknowns", [])
    )
    languages = set(base.get("repository", {}).get("languages", []))
    tool_versions = dict(base.get("repository", {}).get("tool_versions", {}))

    for inst in instances[1:]:
        repo = inst.get("repository", {})
        languages.update(repo.get("languages", []))
        tool_versions.update(repo.get("tool_versions", {}))

        for ent in inst.get("entities", []):
            existing = entities.get(ent["id"])
            if existing is None:
                entities[ent["id"]] = copy.deepcopy(ent)
                continue
            existing["evidence"] = _merge_evidence(existing.get("evidence", []),
                                                   ent.get("evidence", []))
            if CONFIDENCE_RANK[ent["confidence"]] > CONFIDENCE_RANK[existing["confidence"]]:
                existing["confidence"] = ent["confidence"]
            existing.setdefault("attributes", {}).update(ent.get("attributes", {}))
            if existing.get("kind") != ent.get("kind"):
                reason = "Adapters disagree about the entity kind."
                cid = _conflict_id(ent["id"], reason)
                if cid not in conflicts:
                    conflicts[cid] = {
                        "id": cid,
                        "subject": ent["id"],
                        "claims": [
                            _claim(existing.get("attributes", {}).get("tool", "existing"),
                                   {"kind": existing.get("kind")},
                                   existing["confidence"], existing.get("evidence", [])),
                            _claim(ent.get("attributes", {}).get("tool", "new"),
                                   {"kind": ent.get("kind")},
                                   ent["confidence"], ent.get("evidence", [])),
                        ],
                        "resolution": {
                            "status": "unresolved",
                            "chosen": None,
                            "reason": reason,
                        },
                    }

        for edge in inst.get("edges", []):
            key = (edge["from"], edge["to"], edge["kind"])
            existing = edges.get(key)
            if existing is None:
                edges[key] = copy.deepcopy(edge)
                continue
            existing["evidence"] = _merge_evidence(existing.get("evidence", []),
                                                   edge.get("evidence", []))
            if CONFIDENCE_RANK[edge["confidence"]] > CONFIDENCE_RANK[existing["confidence"]]:
                existing["confidence"] = edge["confidence"]
            existing.setdefault("attributes", {})
            existing["attributes"].update(edge.get("attributes", {}))
            existing["attributes"]["occurrence_count"] = (
                existing["attributes"].get("occurrence_count", 1)
                + edge.get("attributes", {}).get("occurrence_count", 1)
            )

        for conflict in inst.get("conflicts", []):
            conflicts.setdefault(conflict["id"], copy.deepcopy(conflict))
        for unknown in inst.get("unknowns", []):
            unknowns.setdefault(unknown["id"], copy.deepcopy(unknown))

    coverage = base.get("coverage", {})
    total = max(i.get("coverage", {}).get("files_total", 0) for i in instances)
    analyzed = max(i.get("coverage", {}).get("files_analyzed", 0) for i in instances)
    skipped = max(0, total - analyzed)

    out = {
        "schema_version": "1.0.0",
        "repository": {
            "commit": next(iter(commits)),
            "root": base.get("repository", {}).get("root", "."),
            "vcs": "git",
            "languages": sorted(languages),
            "tool_versions": tool_versions,
        },
        "entities": sorted(entities.values(), key=lambda e: e["id"]),
        "edges": sorted(edges.values(), key=lambda e: e["id"]),
        "coverage": {
            "files_total": total,
            "files_analyzed": analyzed,
            "files_skipped": skipped,
            "entry_points_identified": max(
                i.get("coverage", {}).get("entry_points_identified", 0) for i in instances
            ),
            "data_stores_identified": max(
                i.get("coverage", {}).get("data_stores_identified", 0) for i in instances
            ),
            "unknowns_count": len(unknowns),
        },
        "conflicts": sorted(conflicts.values(), key=lambda c: c["id"]),
        "unknowns": sorted(unknowns.values(), key=lambda u: u["id"]),
    }
    return out


def overlap(a: dict, b: dict) -> dict:
    ae = {e["id"] for e in a.get("entities", [])}
    be = {e["id"] for e in b.get("entities", [])}
    aedge = {(e["from"], e["to"], e["kind"]) for e in a.get("edges", [])}
    bedge = {(e["from"], e["to"], e["kind"]) for e in b.get("edges", [])}
    return {
        "entities_a": len(ae),
        "entities_b": len(be),
        "entities_common": len(ae & be),
        "entity_jaccard": len(ae & be) / len(ae | be) if ae | be else 0,
        "edges_a": len(aedge),
        "edges_b": len(bedge),
        "edges_common": len(aedge & bedge),
        "edge_jaccard": len(aedge & bedge) / len(aedge | bedge) if aedge | bedge else 0,
    }
