"""Evidence model builders shared by every adapter."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Iterable

from .canonical import canonical_path, short_hash

CONFIDENCE_RANK = {"hypothesis": 0, "inferred": 1, "extracted": 2}
MAX_EVIDENCE_PER_EDGE = 10


def span(start_line: int, end_line: int, start_col: int | None = None,
         end_col: int | None = None, one_based: bool = True) -> dict:
    if one_based:
        start = max(1, int(start_line))
        end = max(start, int(end_line))
    else:
        start = max(1, int(start_line) + 1)
        end = max(start, int(end_line) + 1)
    out = {"start_line": start, "end_line": end}
    if start_col is not None:
        out["start_col"] = int(start_col)
    if end_col is not None:
        out["end_col"] = int(end_col)
    return out


def evidence(tool: str, tool_version: str, type_: str, path: str, commit: str,
             span_obj: dict | None = None, extractor: str | None = None,
             note: str | None = None, snippet_hash: str | None = None) -> dict:
    ev = {
        "tool": tool,
        "tool_version": tool_version or "unknown",
        "type": type_,
        "path": canonical_path(path),
        "commit": commit,
    }
    if span_obj:
        ev["span"] = span_obj
    if extractor:
        ev["extractor"] = extractor
    if note:
        ev["note"] = note
    if snippet_hash:
        ev["snippet_hash"] = snippet_hash
    return ev


def _ev_key(ev: dict) -> tuple:
    s = ev.get("span") or {}
    return (ev.get("tool"), ev.get("path"), s.get("start_line"), s.get("end_line"), ev.get("type"))


class Model:
    """Accumulates entities, edges, conflicts, and unknowns."""

    def __init__(self, commit: str, root: str = ".", languages: Iterable[str] = (),
                 tool_versions: dict | None = None):
        self.commit = commit
        self.root = root
        self.languages = sorted(set(languages))
        self.tool_versions = dict(tool_versions or {})
        self.entities: OrderedDict[str, dict] = OrderedDict()
        self.edges: OrderedDict[tuple, dict] = OrderedDict()
        self.conflicts: OrderedDict[str, dict] = OrderedDict()
        self.unknowns: OrderedDict[str, dict] = OrderedDict()

    # ---------- entities ----------
    def add_entity(self, entity_id: str, kind: str, name: str, confidence: str,
                   evidence_items: list[dict], qualified_name: str | None = None,
                   language: str | None = None, path: str | None = None,
                   span_obj: dict | None = None, parent_id: str | None = None,
                   attributes: dict | None = None) -> dict:
        if not evidence_items:
            raise ValueError(f"entity {entity_id} has no evidence")
        entity = {
            "id": entity_id,
            "kind": kind,
            "name": name,
            "confidence": confidence,
            "evidence": [],
        }
        if qualified_name:
            entity["qualified_name"] = qualified_name
        if language:
            entity["language"] = language
        if path:
            entity["path"] = canonical_path(path)
        if span_obj:
            entity["span"] = span_obj
        if parent_id:
            entity["parent_id"] = parent_id
        if attributes:
            entity["attributes"] = attributes
        existing = self.entities.get(entity_id)
        if existing is None:
            entity["evidence"] = list(evidence_items)
            self.entities[entity_id] = entity
            return entity
        # merge evidence and keep the stronger confidence
        existing["evidence"] = self._merge_evidence(existing["evidence"], evidence_items)
        if CONFIDENCE_RANK[confidence] > CONFIDENCE_RANK[existing["confidence"]]:
            existing["confidence"] = confidence
        if existing.get("kind") != kind:
            self.add_conflict(
                entity_id,
                [
                    self._claim(entity_id, existing.get("attributes", {}).get("tool", "existing"),
                                {"kind": existing.get("kind")}, existing["confidence"],
                                existing.get("evidence", [])),
                    self._claim(entity_id, (attributes or {}).get("tool", "new"),
                                {"kind": kind}, confidence, evidence_items),
                ],
                "Tools disagree about the entity kind.",
            )
        return existing

    # ---------- edges ----------
    def add_edge(self, from_id: str, to_id: str, kind: str, confidence: str,
                 evidence_items: list[dict], attributes: dict | None = None) -> dict | None:
        if from_id == to_id:
            return None
        if from_id not in self.entities or to_id not in self.entities:
            return None
        key = (from_id, to_id, kind)
        existing = self.edges.get(key)
        if existing is not None:
            existing["evidence"] = self._merge_evidence(existing["evidence"], evidence_items)
            existing.setdefault("attributes", {})
            existing["attributes"]["occurrence_count"] = existing["attributes"].get("occurrence_count", 1) + 1
            if CONFIDENCE_RANK[confidence] > CONFIDENCE_RANK[existing["confidence"]]:
                existing["confidence"] = confidence
            return existing
        edge = {
            "id": f"edge:{from_id}|{kind}|{to_id}",
            "from": from_id,
            "to": to_id,
            "kind": kind,
            "confidence": confidence,
            "evidence": list(evidence_items),
        }
        if attributes:
            edge["attributes"] = dict(attributes)
        edge["attributes"] = edge.get("attributes", {})
        edge["attributes"]["occurrence_count"] = 1
        self.edges[key] = edge
        return edge

    # ---------- conflicts / unknowns ----------
    def add_conflict(self, subject: str, claims: list[dict], reason: str) -> dict:
        cid = f"conflict:{short_hash(subject + '|' + reason)}"
        if cid not in self.conflicts:
            self.conflicts[cid] = {
                "id": cid,
                "subject": subject,
                "claims": claims,
                "resolution": {
                    "status": "unresolved",
                    "chosen": None,
                    "reason": reason,
                },
            }
        return self.conflicts[cid]

    def add_unknown(self, question: str, impact: str = "medium",
                    subject: str | None = None, owner: str = "unassigned",
                    evidence_items: list[dict] | None = None) -> dict:
        uid = f"unknown:{short_hash(question + '|' + (subject or ''))}"
        if uid not in self.unknowns:
            item = {
                "id": uid,
                "question": question,
                "impact": impact,
                "owner": owner,
            }
            if subject:
                item["subject"] = subject
            if evidence_items:
                item["evidence"] = evidence_items
            self.unknowns[uid] = item
        return self.unknowns[uid]

    # ---------- output ----------
    def to_dict(self, files_total: int, files_analyzed: int, files_skipped: int,
                entry_points: int = 0, data_stores: int = 0) -> dict:
        entities = sorted(self.entities.values(), key=lambda e: e["id"])
        edges = sorted(self.edges.values(), key=lambda e: e["id"])
        conflicts = sorted(self.conflicts.values(), key=lambda c: c["id"])
        unknowns = sorted(self.unknowns.values(), key=lambda u: u["id"])
        return {
            "schema_version": "1.0.0",
            "repository": {
                "commit": self.commit,
                "root": self.root,
                "vcs": "git",
                "languages": self.languages,
                "tool_versions": self.tool_versions,
            },
            "entities": entities,
            "edges": edges,
            "coverage": {
                "files_total": files_total,
                "files_analyzed": files_analyzed,
                "files_skipped": files_skipped,
                "entry_points_identified": entry_points,
                "data_stores_identified": data_stores,
                "unknowns_count": len(unknowns),
            },
            "conflicts": conflicts,
            "unknowns": unknowns,
        }

    def write(self, path: str, **coverage) -> dict:
        instance = self.to_dict(**coverage)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(instance, fh, indent=2)
            fh.write("\n")
        return instance

    # ---------- helpers ----------
    @staticmethod
    def _merge_evidence(existing: list[dict], new: list[dict]) -> list[dict]:
        seen = {_ev_key(e) for e in existing}
        out = list(existing)
        for ev in new:
            key = _ev_key(ev)
            if key not in seen:
                out.append(ev)
                seen.add(key)
        return out[:MAX_EVIDENCE_PER_EDGE]

    @staticmethod
    def _claim(subject: str, tool: str, value: dict, confidence: str,
               evidence_items: list[dict]) -> dict:
        return {
            "claim_id": f"claim:{short_hash(subject + '|' + tool + '|' + json.dumps(value, sort_keys=True))}",
            "tool": tool or "unknown",
            "value": value,
            "confidence": confidence,
            "evidence": evidence_items,
        }
