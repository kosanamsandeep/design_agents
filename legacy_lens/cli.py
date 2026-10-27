"""Legacy Lens pipeline CLI.

Examples:
    python -m legacy_lens.cli run --repo testdata/rocketmq \
        --index artifacts/rocketmq.scip --out-dir artifacts
    python -m legacy_lens.cli validate --model artifacts/code.graph.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .adapters.scip_java import build as build_scip
from .adapters.tree_sitter_java import build as build_tree_sitter
from .architecture import load, write_hld, write_lld
from .merge import merge_instances, overlap
from .validation import validate_file


def _edge_kinds(value: str) -> set[str]:
    return {v.strip() for v in value.split(",") if v.strip()}


def cmd_scip(args) -> int:
    out = build_scip(
        args.repo, args.index, args.out,
        include_external=args.include_external,
        include_files=args.include_files,
        edge_kinds=_edge_kinds(args.edge_kinds),
        include_tests=args.include_tests,
    )
    print(json.dumps({
        "artifact": args.out,
        "entities": len(out["entities"]),
        "edges": len(out["edges"]),
        "coverage": out["coverage"],
    }, indent=2))
    return 0


def cmd_treesitter(args) -> int:
    out = build_tree_sitter(args.repo, args.out)
    print(json.dumps({
        "artifact": args.out,
        "entities": len(out["entities"]),
        "edges": len(out["edges"]),
        "coverage": out["coverage"],
    }, indent=2))
    return 0


def cmd_merge(args) -> int:
    instances = [load(p) for p in args.inputs]
    merged = merge_instances(instances)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    report = {
        "artifact": args.out,
        "entities": len(merged["entities"]),
        "edges": len(merged["edges"]),
        "conflicts": len(merged["conflicts"]),
        "unknowns": len(merged["unknowns"]),
        "overlap": overlap(instances[0], instances[1]) if len(instances) > 1 else {},
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_hld(args) -> int:
    hld = write_hld(args.model, args.out_dir)
    print(json.dumps({
        "out_dir": args.out_dir,
        "containers": len(hld["containers"]),
        "edges": len(hld["edges"]),
        "entry_points": len(hld["entry_points"]),
    }, indent=2))
    return 0


def cmd_lld(args) -> int:
    lld = write_lld(args.model, args.module, args.out_dir)
    print(json.dumps({
        "out_dir": args.out_dir,
        "module": args.module,
        "classes": len(lld["classes"]),
        "flows": len(lld["flows"]),
        "edges": len(lld["edges"]),
    }, indent=2))
    return 0


def cmd_validate(args) -> int:
    errors = validate_file(args.model)
    if errors:
        print(f"FAIL {args.model}")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"ok   {args.model}")
    return 0


def cmd_run(args) -> int:
    started = time.time()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scip_path = out_dir / "evidence.scip.json"
    ts_path = out_dir / "evidence.treesitter.json"
    merged_path = out_dir / "code.graph.json"

    print("[1/5] scip adapter", flush=True)
    scip = build_scip(
        args.repo, args.index, scip_path,
        include_external=args.include_external,
        include_files=args.include_files,
        edge_kinds=_edge_kinds(args.edge_kinds),
        include_tests=args.include_tests,
    )
    print(f"      entities={len(scip['entities'])} edges={len(scip['edges'])}", flush=True)

    print("[2/5] tree-sitter adapter", flush=True)
    ts = build_tree_sitter(args.repo, ts_path)
    print(f"      entities={len(ts['entities'])} edges={len(ts['edges'])}", flush=True)

    print("[3/5] merge + validate", flush=True)
    merged = merge_instances([scip, ts])
    merged_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    errors = validate_file(str(merged_path))
    if errors:
        print(f"      merge validation failed: {errors[:5]}")
        return 1
    print(f"      entities={len(merged['entities'])} edges={len(merged['edges'])}", flush=True)

    print("[4/5] HLD baseline", flush=True)
    hld = write_hld(merged_path, out_dir / "hld")
    print(f"      containers={len(hld['containers'])} edges={len(hld['edges'])}", flush=True)

    print("[5/5] LLD baseline", flush=True)
    modules = [m.strip() for m in (args.modules or "").split(",") if m.strip()]
    if not modules:
        modules = [c["module"] for c in sorted(hld["containers"],
                                               key=lambda c: -c["classes"])[:3]]
    lld_summary = {}
    for module in modules:
        lld = write_lld(merged_path, module, out_dir / "lld")
        lld_summary[module] = {
            "classes": len(lld["classes"]),
            "flows": len(lld["flows"]),
            "edges": len(lld["edges"]),
        }
        print(f"      {module}: classes={len(lld['classes'])} flows={len(lld['flows'])}", flush=True)

    manifest = {
        "repository": merged["repository"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 2),
        "artifacts": {
            "scip": str(scip_path),
            "treesitter": str(ts_path),
            "graph": str(merged_path),
            "hld": str(out_dir / "hld" / "c4.model.json"),
            "lld": str(out_dir / "lld"),
        },
        "counts": {
            "scip_entities": len(scip["entities"]),
            "scip_edges": len(scip["edges"]),
            "treesitter_entities": len(ts["entities"]),
            "treesitter_edges": len(ts["edges"]),
            "merged_entities": len(merged["entities"]),
            "merged_edges": len(merged["edges"]),
            "hld_containers": len(hld["containers"]),
            "lld": lld_summary,
        },
        "overlap": overlap(scip, ts),
        "coverage": merged["coverage"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                           encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="legacy-lens")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scip", help="Build evidence from a SCIP index")
    s.add_argument("--repo", required=True)
    s.add_argument("--index", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--include-external", action="store_true")
    s.add_argument("--include-files", action="store_true")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--edge-kinds", default="calls,uses,extends,implements")
    s.set_defaults(func=cmd_scip)

    s = sub.add_parser("treesitter", help="Build evidence from Java sources")
    s.add_argument("--repo", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_treesitter)

    s = sub.add_parser("merge", help="Merge evidence models")
    s.add_argument("--inputs", nargs="+", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_merge)

    s = sub.add_parser("hld", help="Generate the deterministic HLD baseline")
    s.add_argument("--model", required=True)
    s.add_argument("--out-dir", required=True)
    s.set_defaults(func=cmd_hld)

    s = sub.add_parser("lld", help="Generate the deterministic LLD baseline")
    s.add_argument("--model", required=True)
    s.add_argument("--module", required=True)
    s.add_argument("--out-dir", required=True)
    s.set_defaults(func=cmd_lld)

    s = sub.add_parser("validate", help="Validate an evidence model")
    s.add_argument("--model", required=True)
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("run", help="Run adapters, merge, HLD, and LLD")
    s.add_argument("--repo", required=True)
    s.add_argument("--index", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--modules", default="")
    s.add_argument("--include-external", action="store_true")
    s.add_argument("--include-files", action="store_true")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--edge-kinds", default="calls,uses,extends,implements")
    s.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
