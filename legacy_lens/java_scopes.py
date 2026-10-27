"""Lightweight Java scope map for attributing SCIP references.

scip-java does not populate Occurrence.enclosing_range, so a reference cannot be
attributed to its enclosing method from SCIP alone. tree-sitter already gives us
exact class/method spans; this module maps positions to the innermost scope and
its qualified name (the same form the SCIP adapter assigns).

The traversal is iterative: deeply nested Java ASTs can otherwise exhaust the
C stack when mixed with tree-sitter node objects.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_java
from tree_sitter import Language, Parser

from .canonical import canonical_path

CLASS_NODES = {"class_declaration", "interface_declaration", "enum_declaration"}
METHOD_NODES = {"method_declaration", "constructor_declaration"}


def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _identifier(node) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            return _text(child)
    return None


def _package(root) -> str:
    for child in root.children:
        if child.type == "package_declaration":
            return _text(child).replace("package", "").replace(";", "").strip()
    return ""


def _scopes_for(root) -> list:
    package = _package(root)
    scopes: list = []
    stack = [(child, package, []) for child in reversed(root.children)]
    while stack:
        node, package, classes = stack.pop()
        if node.type in CLASS_NODES:
            name = _identifier(node)
            if name:
                qname = ".".join(filter(None, [package, *classes, name]))
                scopes.append((node.start_point.row, node.start_point.column,
                               node.end_point.row, node.end_point.column, qname))
                body = next((c for c in node.children
                             if c.type in ("class_body", "interface_body", "enum_body")), None)
                if body is not None:
                    for child in reversed(body.children):
                        stack.append((child, package, [*classes, name]))
            continue
        if node.type in METHOD_NODES:
            name = _identifier(node)
            if name and classes:
                qname = ".".join(filter(None, [package, *classes])) + "#" + name
                scopes.append((node.start_point.row, node.start_point.column,
                               node.end_point.row, node.end_point.column, qname))
            body = next((c for c in node.children
                         if c.type in ("block", "constructor_body")), None)
            if body is not None:
                for child in reversed(body.children):
                    stack.append((child, package, classes))
            continue
        for child in reversed(node.children):
            stack.append((child, package, classes))
    return scopes


def collect_scopes(repo: str | Path, relative_paths: list[str]) -> dict[str, list]:
    root = Path(repo)
    language = Language(tree_sitter_java.language())
    out: dict[str, list] = {}
    for rel in relative_paths:
        path = root / rel
        if not path.exists() or path.suffix != ".java":
            continue
        try:
            parser = Parser(language)
            tree = parser.parse(path.read_bytes())
            scopes = _scopes_for(tree.root_node)
            if scopes:
                out[canonical_path(rel)] = scopes
        except Exception:
            continue
    return out


def find_scope(scopes: list, line: int, col: int) -> str | None:
    """Return the qualified name of the smallest scope containing (line, col)."""
    best = None
    best_span = None
    for sl, sc, el, ec, qname in scopes:
        if (sl, sc) <= (line, col) <= (el, ec):
            span = (el - sl) * 100000 + max(0, ec - sc)
            if best_span is None or span < best_span:
                best_span = span
                best = qname
    return best
