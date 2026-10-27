"""Build the schema contract fixtures from valid/minimal.json.

Run from the repo root:  python3 docs/fixtures/build_fixtures.py
"""
import copy
import json
import os

HERE = os.path.dirname(__file__)


def load():
    with open(os.path.join(HERE, "valid", "minimal.json"), encoding="utf-8") as fh:
        return json.load(fh)


def write(subdir, name, obj):
    path = os.path.join(HERE, subdir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")


def make(fn):
    d = copy.deepcopy(load())
    fn(d)
    return d


def missing_tool_version(d):
    del d["entities"][0]["evidence"][0]["tool_version"]


def source_span_missing_span(d):
    del d["entities"][1]["evidence"][0]["span"]


def unresolved_with_chosen(d):
    d["conflicts"][0]["resolution"]["chosen"] = "claim:owner-billing"


def human_no_reviewer(d):
    d["conflicts"][0]["resolution"] = {
        "status": "resolved",
        "chosen": "claim:owner-billing",
        "by": "human",
        "reason": "Billing owner confirmed.",
    }


def rule_not_versioned(d):
    d["conflicts"][0]["resolution"] = {
        "status": "resolved",
        "chosen": "claim:owner-billing",
        "by": "rule",
        "rule": "static-precedence",
        "reason": "SCIP outranks tree-sitter.",
    }


def dangling_edge(d):
    d["edges"][0]["to"] = "table:postgres:missing"


def bad_coverage(d):
    d["coverage"]["files_skipped"] = 10
    d["coverage"]["unknowns_count"] = 0


def duplicate_entity_id(d):
    d["entities"].append(copy.deepcopy(d["entities"][0]))


def resolved_unknown_claim(d):
    d["conflicts"][0]["resolution"] = {
        "status": "resolved",
        "chosen": "claim:nope",
        "by": "rule",
        "rule": "static-precedence@v1",
        "reason": "Rule applied.",
    }


def unknown_subject(d):
    d["unknowns"][0]["subject"] = "table:postgres:missing"


def duplicate_claim_id(d):
    d["conflicts"][0]["claims"][1]["claim_id"] = "claim:owner-billing"


def evidence_backslash(d):
    d["entities"][0]["evidence"][0]["path"] = "deploy\\k8s\\billing.yaml"


def evidence_absolute(d):
    d["entities"][0]["evidence"][0]["path"] = "/deploy/k8s/billing.yaml"


def parent_dangling(d):
    d["entities"][1]["parent_id"] = "module:python:missing"


def resolved_human(d):
    d["conflicts"][0]["resolution"] = {
        "status": "resolved",
        "chosen": "claim:owner-billing",
        "by": "human",
        "reviewer": "review:1234",
        "reason": "Billing owner confirmed the data model.",
    }


def resolved_rule(d):
    d["conflicts"][0]["resolution"] = {
        "status": "resolved",
        "chosen": "claim:owner-billing",
        "by": "rule",
        "rule": "static-precedence@v1",
        "reason": "SCIP outranks tree-sitter for static structure.",
    }


INVALID = {
    "missing-tool-version.json": missing_tool_version,
    "source-span-missing-span.json": source_span_missing_span,
    "unresolved-with-chosen.json": unresolved_with_chosen,
    "human-no-reviewer.json": human_no_reviewer,
    "rule-not-versioned.json": rule_not_versioned,
    "dangling-edge.json": dangling_edge,
    "bad-coverage.json": bad_coverage,
    "duplicate-entity-id.json": duplicate_entity_id,
    "resolved-unknown-claim.json": resolved_unknown_claim,
    "unknown-subject.json": unknown_subject,
    "duplicate-claim-id.json": duplicate_claim_id,
    "evidence-backslash.json": evidence_backslash,
    "evidence-absolute-path.json": evidence_absolute,
    "parent-dangling.json": parent_dangling,
}

VALID = {
    "resolved-human.json": resolved_human,
    "resolved-rule.json": resolved_rule,
}


if __name__ == "__main__":
    for name, fn in INVALID.items():
        write("invalid", name, make(fn))
    for name, fn in VALID.items():
        write("valid", name, make(fn))
    print(f"wrote {len(INVALID)} invalid and {len(VALID)} valid fixtures")
