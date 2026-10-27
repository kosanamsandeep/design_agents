"""Contract tests for evidence-schema v1.

Run from the repo root:
    python3 docs/contract_tests.py

The suite checks:
  1. valid fixtures pass JSON Schema + semantic validation
  2. invalid fixtures fail with the expected rule
  3. canonicalization fixtures match the reference implementation

v1 is not frozen until this suite passes.
"""

from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

import canonicalize  # noqa: E402
import validate_evidence  # noqa: E402

EXPECTED_INVALID = {
    "bad-coverage.json": "coverage",
    "dangling-edge.json": "does not reference an existing entity",
    "duplicate-claim-id.json": "duplicate claim_id",
    "duplicate-entity-id.json": "duplicate entity id",
    "evidence-absolute-path.json": "does not match",
    "evidence-backslash.json": "backslash",
    "human-no-reviewer.json": "reviewer",
    "missing-tool-version.json": "tool_version",
    "parent-dangling.json": "parent_id",
    "resolved-unknown-claim.json": "chosen",
    "rule-not-versioned.json": "does not match",
    "source-span-missing-span.json": "span",
    "unknown-subject.json": "unknown",
    "unresolved-with-chosen.json": "chosen",
}


def main() -> int:
    schema = validate_evidence.load_schema()
    failures: list[str] = []

    valid_dir = os.path.join(HERE, "fixtures", "valid")
    invalid_dir = os.path.join(HERE, "fixtures", "invalid")

    for path in sorted(glob.glob(os.path.join(valid_dir, "*.json"))):
        errors = validate_evidence.validate_file(path, schema)
        if errors:
            failures.append(f"valid fixture failed: {path}")
            failures.extend(f"  - {e}" for e in errors)

    invalid_paths = sorted(glob.glob(os.path.join(invalid_dir, "*.json")))
    for path in invalid_paths:
        name = os.path.basename(path)
        if name not in EXPECTED_INVALID:
            failures.append(f"invalid fixture has no expected-rule entry: {name}")
            continue
        errors = validate_evidence.validate_file(path, schema)
        if not errors:
            failures.append(f"invalid fixture unexpectedly passed: {name}")
            continue
        needle = EXPECTED_INVALID[name]
        joined = "\n".join(errors)
        if needle not in joined:
            failures.append(f"invalid fixture failed for the wrong reason: {name} (expected {needle!r})")
            failures.extend(f"  - {e}" for e in errors)

    with open(os.path.join(HERE, "canonicalization-fixtures.json"), encoding="utf-8") as fh:
        canon = json.load(fh)

    for case in canon["path"]:
        got = canonicalize.canonical_path(case["input"])
        if got != case["expected"]:
            failures.append(f"path canonicalization: {case['input']!r} -> {got!r}, expected {case['expected']!r}")

    for case in canon["route"]:
        got = canonicalize.canonical_route(case["method"], case["path"])
        if got != case["expected"]:
            failures.append(f"route canonicalization: {case['method']} {case['path']!r} -> {got!r}, expected {case['expected']!r}")

    for case in canon["qualified_name"]:
        got = canonicalize.canonical_qualified_name(
            case["language"], case["module"], case["name"], case.get("parameter_types") or None
        )
        if got != case["expected"]:
            failures.append(f"qualified-name canonicalization: {case['name']!r} -> {got!r}, expected {case['expected']!r}")

    valid_count = len(glob.glob(os.path.join(valid_dir, "*.json")))
    invalid_count = len(invalid_paths)
    if failures:
        print(f"FAILED ({len(failures)} issue(s))")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"ok: {valid_count} valid fixtures, {invalid_count} invalid fixtures, "
          f"{len(canon['path']) + len(canon['route']) + len(canon['qualified_name'])} canonicalization cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
