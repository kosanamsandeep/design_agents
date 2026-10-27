"""Validate an evidence model instance.

JSON Schema validates shape. This module adds the semantics the schema cannot
express: referential integrity, ID uniqueness, conflict resolution references,
evidence path rules, and coverage arithmetic.

Usage:
    python3 docs/validate_evidence.py docs/fixtures/valid/minimal.json
    python3 docs/validate_evidence.py --all docs/fixtures/valid
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import jsonschema


def load_schema(path: str | None = None) -> dict:
    path = path or os.path.join(os.path.dirname(__file__), "evidence-schema.v1.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _evidence_items(instance: dict):
    for entity in instance.get("entities", []):
        for ev in entity.get("evidence", []):
            yield f"entity {entity.get('id')}", ev
        for alt in entity.get("alternatives", []):
            for ev in alt.get("evidence", []):
                yield f"entity {entity.get('id')} alternative {alt.get('claim_id')}", ev
    for edge in instance.get("edges", []):
        for ev in edge.get("evidence", []):
            yield f"edge {edge.get('id')}", ev
        for alt in edge.get("alternatives", []):
            for ev in alt.get("evidence", []):
                yield f"edge {edge.get('id')} alternative {alt.get('claim_id')}", ev
    for conflict in instance.get("conflicts", []):
        for claim in conflict.get("claims", []):
            for ev in claim.get("evidence", []):
                yield f"conflict {conflict.get('id')} claim {claim.get('claim_id')}", ev
    for unknown in instance.get("unknowns", []):
        for ev in unknown.get("evidence", []):
            yield f"unknown {unknown.get('id')}", ev


def validate_instance(instance: dict, schema: dict | None = None) -> list[str]:
    """Return a list of human-readable semantic errors. Empty means valid."""
    schema = schema or load_schema()
    errors: list[str] = []

    try:
        jsonschema.validate(instance, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        return [f"schema: {exc.message} (at {location})"]

    entities = instance.get("entities", [])
    edges = instance.get("edges", [])

    entity_ids: list[str] = [e.get("id") for e in entities]
    edge_ids: list[str] = [e.get("id") for e in edges]
    entity_set = set(entity_ids)
    edge_set = set(edge_ids)
    all_ids = entity_set | edge_set

    seen: set[str] = set()
    for eid in entity_ids:
        if eid in seen:
            errors.append(f"duplicate entity id: {eid}")
        seen.add(eid)
    seen = set()
    for eid in edge_ids:
        if eid in seen:
            errors.append(f"duplicate edge id: {eid}")
        seen.add(eid)

    for entity in entities:
        parent = entity.get("parent_id")
        if parent is not None and parent not in entity_set:
            errors.append(f"entity {entity.get('id')} parent_id does not reference an existing entity: {parent}")

    for edge in edges:
        if edge.get("from") not in entity_set:
            errors.append(f"edge {edge.get('id')} from does not reference an existing entity: {edge.get('from')}")
        if edge.get("to") not in entity_set:
            errors.append(f"edge {edge.get('id')} to does not reference an existing entity: {edge.get('to')}")

    for conflict in instance.get("conflicts", []):
        cid = conflict.get("id")
        subject = conflict.get("subject")
        if subject not in all_ids:
            errors.append(f"conflict {cid} subject does not reference an existing entity or edge: {subject}")
        claims = conflict.get("claims", [])
        claim_ids = [c.get("claim_id") for c in claims]
        if len(claim_ids) != len(set(claim_ids)):
            errors.append(f"conflict {cid} has duplicate claim_id values")
        resolution = conflict.get("resolution", {})
        status = resolution.get("status")
        chosen = resolution.get("chosen")
        if status == "resolved":
            if chosen not in claim_ids:
                errors.append(f"conflict {cid} chosen does not reference one of its claims: {chosen}")
        elif status == "unresolved" and chosen is not None:
            errors.append(f"conflict {cid} is unresolved but chosen is set: {chosen}")

    for unknown in instance.get("unknowns", []):
        subject = unknown.get("subject")
        if subject is not None and subject not in all_ids:
            errors.append(f"unknown {unknown.get('id')} subject does not reference an existing entity or edge: {subject}")

    coverage = instance.get("coverage", {})
    total = coverage.get("files_total", 0)
    analyzed = coverage.get("files_analyzed", 0)
    skipped = coverage.get("files_skipped", 0)
    if analyzed + skipped != total:
        errors.append(
            f"coverage: files_analyzed ({analyzed}) + files_skipped ({skipped}) != files_total ({total})"
        )
    if coverage.get("unknowns_count") != len(instance.get("unknowns", [])):
        errors.append(
            f"coverage: unknowns_count ({coverage.get('unknowns_count')}) != len(unknowns) ({len(instance.get('unknowns', []))})"
        )

    for context, ev in _evidence_items(instance):
        path = ev.get("path", "")
        if path.startswith("/"):
            errors.append(f"{context}: evidence path is absolute: {path}")
        if path.startswith("./"):
            errors.append(f"{context}: evidence path starts with './': {path}")
        if "\\" in path:
            errors.append(f"{context}: evidence path contains a backslash: {path}")
        if ev.get("type") == "source_span" and not ev.get("span"):
            errors.append(f"{context}: source_span evidence is missing a span")

    return errors


def validate_file(path: str, schema: dict | None = None) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        instance = json.load(fh)
    return validate_instance(instance, schema)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Legacy Lens evidence model instance.")
    parser.add_argument("files", nargs="*", help="JSON instance files")
    parser.add_argument("--all", dest="directory", help="Validate every *.json in a directory")
    args = parser.parse_args(argv)

    paths = list(args.files)
    if args.directory:
        paths.extend(sorted(glob.glob(os.path.join(args.directory, "*.json"))))

    if not paths:
        parser.error("provide at least one file or --all <directory>")

    schema = load_schema()
    failed = 0
    for path in paths:
        errors = validate_file(path, schema)
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"ok   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
