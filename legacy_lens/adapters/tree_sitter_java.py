"""tree-sitter Java adapter: syntax-level entities, calls, imports, routes.

This is deliberately syntax-only. It creates classes/interfaces/enums/methods/
fields, extends/implements edges, calls resolved by unique name, imports, and
Spring route annotations. Unresolved calls are counted, not guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter
import tree_sitter_java
from tree_sitter import Language, Parser

from ..canonical import canonical_route, entity_id, short_hash
from ..gitinfo import commit, java_files
from ..model import Model, evidence, span

ROUTE_ANN = {
    "GetMapping": "get",
    "PostMapping": "post",
    "PutMapping": "put",
    "DeleteMapping": "delete",
    "PatchMapping": "patch",
    "RequestMapping": "any",
}

CLASS_NODES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
}

EXCLUDED_PARTS = {"target", "build", "out", ".git", "generated-sources",
                  "generated-test-sources", ".gradle", "node_modules"}


def _excluded(rel: str) -> bool:
    if "src/test" in rel or "/test/" in rel:
        return True
    return any(part in EXCLUDED_PARTS for part in rel.split("/"))


@dataclass
class Ref:
    kind: str
    source_id: str
    name: str
    path: str
    start: tuple[int, int]
    end: tuple[int, int]
    extra: dict = field(default_factory=dict)


@dataclass
class Context:
    package: str = ""
    classes: list[tuple[str, str]] = field(default_factory=list)  # (name, entity_id)
    current_method: str | None = None
    class_route_prefix: str = ""

    def class_id(self) -> str | None:
        return self.classes[-1][1] if self.classes else None

    def class_name(self) -> str:
        return ".".join(name for name, _ in self.classes)


def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _identifier(node) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            return _text(child)
    return None


def _first_type(node) -> str | None:
    for child in node.children:
        if child.type in ("type_identifier", "scoped_type_identifier", "generic_type"):
            return _text(child)
    return None


def _span(node) -> dict:
    return span(node.start_point.row, node.end_point.row,
                node.start_point.column, node.end_point.column, one_based=False)


def _annotations(modifiers) -> list:
    if modifiers is None:
        return []
    out = []
    for child in modifiers.children:
        if child.type == "annotation":
            out.append(child)
    return out


def _annotation_name(node) -> str:
    for child in node.children:
        if child.type == "identifier":
            return _text(child)
    return ""


def _annotation_strings(node) -> list[str]:
    out = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "string_literal":
            out.append(_text(n).strip('"'))
        stack.extend(reversed(n.children))
    return out


def _field_name(node) -> str | None:
    for child in node.children:
        if child.type == "variable_declarator":
            return _identifier(child)
    return None


def _call_name(node) -> str | None:
    identifiers = [c for c in node.children if c.type == "identifier"]
    return _text(identifiers[-1]) if identifiers else None


def _object_type(node) -> str | None:
    for child in node.children:
        if child.type in ("type_identifier", "generic_type", "scoped_type_identifier"):
            text = _text(child)
            text = text.split("<", 1)[0]
            return text.split(".")[-1]
    return None


class TreeSitterJavaAdapter:
    def __init__(self, repo: str | Path):
        self.repo = Path(repo)
        self.commit = commit(self.repo)
        self.language = Language(tree_sitter_java.language())
        self.parser = Parser(self.language)
        self.tool_version = "tree-sitter-0.25.2/tree-sitter-java-0.23.5"
        self.model = Model(
            commit=self.commit, root=str(self.repo.resolve()),
            languages=["java"], tool_versions={"tree-sitter": self.tool_version},
        )
        self.class_by_simple: dict[str, list[str]] = {}
        self.methods_by_class: dict[str, dict[str, list[str]]] = {}
        self.methods_by_name: dict[str, list[str]] = {}
        self.files: list[Path] = []
        self.parsed = 0
        self.skipped = 0
        self.test_files = 0
        self.unresolved_calls = 0
        self.refs: list[Ref] = []
        self.file_ids: dict[str, str] = {}
        self.method_ids: dict[str, str] = {}

    # ---------- helpers ----------
    def _file_entity(self, path: str, node) -> str:
        if path in self.file_ids:
            return self.file_ids[path]
        eid = entity_id("file", "java", path, Path(path).name)
        sp = _span(node)
        ev = evidence("tree-sitter", self.tool_version, "source_span", path,
                      self.commit, sp, extractor="tree-sitter-java")
        self.model.add_entity(eid, "file", Path(path).name, "extracted", [ev],
                              qualified_name=path, language="java", path=path,
                              span_obj=sp, attributes={"tool": "tree-sitter"})
        self.file_ids[path] = eid
        return eid

    def _add_ref(self, ref: Ref):
        self.refs.append(ref)

    # ---------- pass 1 ----------
    def _visit(self, node, path: str, ctx: Context, current_id: str | None):
        if node.type == "package_declaration":
            text = _text(node).replace("package", "").replace(";", "").strip()
            if text:
                ctx.package = text
            return
        if node.type == "import_declaration":
            text = _text(node).replace("import", "").replace("static", "").replace(";", "").strip()
            if text and not text.endswith("*"):
                file_id = self._file_entity(path, node)
                self._add_ref(Ref("import", file_id, text, path,
                                  (node.start_point.row, node.start_point.column),
                                  (node.end_point.row, node.end_point.column)))
            return
        if node.type in CLASS_NODES:
            name = _identifier(node)
            if not name:
                return
            kind = CLASS_NODES[node.type]
            qname = ".".join(filter(None, [ctx.package, ctx.class_name(), name]))
            eid = entity_id(kind, "java", path, qname)
            sp = _span(node)
            ev = evidence("tree-sitter", self.tool_version, "source_span", path,
                          self.commit, sp, extractor="tree-sitter-java")
            parent_id = ctx.class_id()
            annotations = _annotations(next((c for c in node.children if c.type == "modifiers"), None))
            attrs = {"tool": "tree-sitter", "syntax_kind": node.type}
            if annotations:
                attrs["annotations"] = [_annotation_name(a) for a in annotations]
            self.model.add_entity(eid, kind, name, "extracted", [ev],
                                  qualified_name=qname, language="java", path=path,
                                  span_obj=sp, parent_id=parent_id, attributes=attrs)
            self.class_by_simple.setdefault(name, []).append(eid)
            # route prefix from class-level @RequestMapping
            class_prefix = ""
            for ann in annotations:
                aname = _annotation_name(ann)
                strings = _annotation_strings(ann)
                if aname == "RequestMapping" and strings:
                    class_prefix = strings[0].rstrip("/")
                    break
            # inheritance refs
            for child in node.children:
                if child.type == "superclass":
                    t = _first_type(child)
                    if t:
                        self._add_ref(Ref("extends", eid, t.split(".")[-1], path,
                                          (child.start_point.row, child.start_point.column),
                                          (child.end_point.row, child.end_point.column)))
                elif child.type in ("super_interfaces", "extends_interfaces"):
                    for sub in child.children:
                        if sub.type == "type_list":
                            for t in sub.children:
                                if t.type in ("type_identifier", "scoped_type_identifier"):
                                    self._add_ref(Ref("implements", eid, _text(t).split(".")[-1],
                                                      path, (t.start_point.row, t.start_point.column),
                                                      (t.end_point.row, t.end_point.column)))
            ctx.classes.append((name, eid))
            old_prefix = ctx.class_route_prefix
            ctx.class_route_prefix = class_prefix
            body = next((c for c in node.children if c.type in
                         ("class_body", "interface_body", "enum_body")), None)
            if body is not None:
                for child in body.children:
                    self._visit(child, path, ctx, eid)
            ctx.class_route_prefix = old_prefix
            ctx.classes.pop()
            return
        if node.type in ("method_declaration", "constructor_declaration"):
            name = _identifier(node)
            if not name or not ctx.classes:
                return
            params = next((c for c in node.children if c.type == "formal_parameters"), None)
            params_text = re.sub(r"\s+", "", _text(params)) if params is not None else ""
            qname = ".".join(filter(None, [ctx.package, ctx.class_name()])) + f"#{name}"
            base = entity_id("method", "java", path, qname)
            if base in self.method_ids and self.method_ids[base] != (params_text or name):
                eid = f"{base}@{short_hash(params_text or name)}"
            else:
                eid = base
                self.method_ids[base] = params_text or name
            sp = _span(node)
            ev = evidence("tree-sitter", self.tool_version, "source_span", path,
                          self.commit, sp, extractor="tree-sitter-java")
            parent_id = ctx.class_id()
            annotations = _annotations(next((c for c in node.children if c.type == "modifiers"), None))
            attrs = {"tool": "tree-sitter", "syntax_kind": node.type,
                     "parameters": params_text}
            if annotations:
                attrs["annotations"] = [_annotation_name(a) for a in annotations]
            self.model.add_entity(eid, "method", name, "extracted", [ev],
                                  qualified_name=qname, language="java", path=path,
                                  span_obj=sp, parent_id=parent_id, attributes=attrs)
            if parent_id:
                self.methods_by_class.setdefault(parent_id, {}).setdefault(name, []).append(eid)
            self.methods_by_name.setdefault(name, []).append(eid)
            for ann in annotations:
                self._route(ann, eid, path, ctx.class_route_prefix, ctx)
            old_method = ctx.current_method
            ctx.current_method = eid
            body = next((c for c in node.children if c.type in ("block", "constructor_body")), None)
            if body is not None:
                for child in body.children:
                    self._visit(child, path, ctx, eid)
            ctx.current_method = old_method
            return
        if node.type == "field_declaration" and ctx.classes:
            name = _field_name(node)
            if name:
                qname = ".".join(filter(None, [ctx.package, ctx.class_name()])) + f"#{name}"
                eid = entity_id("field", "java", path, qname)
                sp = _span(node)
                ev = evidence("tree-sitter", self.tool_version, "source_span", path,
                              self.commit, sp, extractor="tree-sitter-java")
                self.model.add_entity(eid, "field", name, "extracted", [ev],
                                      qualified_name=qname, language="java", path=path,
                                      span_obj=sp, parent_id=ctx.class_id(),
                                      attributes={"tool": "tree-sitter",
                                                  "syntax_kind": node.type})
            return
        if node.type == "method_invocation":
            name = _call_name(node)
            source = ctx.current_method or ctx.class_id()
            if name and source:
                self._add_ref(Ref("call", source, name, path,
                                  (node.start_point.row, node.start_point.column),
                                  (node.end_point.row, node.end_point.column),
                                  {"has_receiver": any(c.type not in ("identifier", "argument_list")
                                                       for c in node.children[:2])}))
            # still walk the receiver and arguments for nested calls
            for child in node.children:
                self._visit(child, path, ctx, current_id)
            return
        if node.type == "object_creation_expression":
            t = _object_type(node)
            source = ctx.current_method or ctx.class_id()
            if t and source:
                self._add_ref(Ref("new", source, t, path,
                                  (node.start_point.row, node.start_point.column),
                                  (node.end_point.row, node.end_point.column)))
            for child in node.children:
                self._visit(child, path, ctx, current_id)
            return
        for child in node.children:
            self._visit(child, path, ctx, current_id)

    # ---------- routes ----------
    def _route(self, ann, source_id: str, path: str, prefix: str, ctx: Context):
        name = _annotation_name(ann)
        method = ROUTE_ANN.get(name)
        if not method:
            return
        strings = _annotation_strings(ann)
        if not strings:
            return
        route_path = strings[0]
        if prefix and not route_path.startswith(prefix):
            route_path = prefix.rstrip("/") + "/" + route_path.lstrip("/")
        canonical = canonical_route(method, route_path)
        rid = canonical
        sp = _span(ann)
        ev = evidence("tree-sitter", self.tool_version, "source_span", path,
                      self.commit, sp, extractor="spring-route")
        self.model.add_entity(rid, "route", canonical, "inferred", [ev],
                              qualified_name=canonical, language="java", path=path,
                              span_obj=sp,
                              attributes={"tool": "tree-sitter",
                                          "annotation": name,
                                          "path": route_path,
                                          "http_method": method})
        self.model.add_edge(source_id, rid, "routes_to", "inferred", [ev],
                            attributes={"classification": "annotation"})

    # ---------- pass 2 ----------
    def _resolve_class(self, simple: str) -> str | None:
        hits = self.class_by_simple.get(simple, [])
        return hits[0] if len(hits) == 1 else None

    def _resolve_method(self, source_id: str, name: str) -> str | None:
        # same class first
        parent = self.model.entities.get(source_id, {}).get("parent_id")
        if parent:
            hits = self.methods_by_class.get(parent, {}).get(name, [])
            if len(hits) == 1:
                return hits[0]
        hits = self.methods_by_name.get(name, [])
        return hits[0] if len(hits) == 1 else None

    def _external_class(self, name: str, ref: Ref) -> str:
        eid = entity_id("class", "java", "external", name, disambiguator=name)
        if eid not in self.model.entities:
            ev = evidence("tree-sitter", self.tool_version, "source_span", ref.path,
                          self.commit, span(ref.start[0], ref.end[0], ref.start[1],
                                            ref.end[1], one_based=False),
                          extractor="tree-sitter-java",
                          note="Referenced type with no definition in the indexed repository.")
            self.model.add_entity(eid, "class", name, "inferred", [ev],
                                  qualified_name=name, language="java", path=ref.path,
                                  attributes={"tool": "tree-sitter", "external": True})
        return eid

    def _resolve_refs(self):
        for ref in self.refs:
            sp = span(ref.start[0], ref.end[0], ref.start[1], ref.end[1], one_based=False)
            ev = evidence("tree-sitter", self.tool_version, "source_span", ref.path,
                          self.commit, sp, extractor="tree-sitter-java")
            if ref.kind in ("extends", "implements"):
                target = self._resolve_class(ref.name)
                if target is None:
                    target = self._external_class(ref.name, ref)
                self.model.add_edge(ref.source_id, target, ref.kind, "extracted", [ev],
                                    attributes={"classification": "syntax"})
            elif ref.kind == "call":
                target = self._resolve_method(ref.source_id, ref.name)
                if target is None:
                    self.unresolved_calls += 1
                    continue
                self.model.add_edge(ref.source_id, target, "calls", "inferred", [ev],
                                    attributes={"classification": "name-resolution"})
            elif ref.kind == "new":
                target = self._resolve_class(ref.name)
                if target is None:
                    self.unresolved_calls += 1
                    continue
                self.model.add_edge(ref.source_id, target, "calls", "inferred", [ev],
                                    attributes={"classification": "constructor"})
            elif ref.kind == "import":
                last = ref.name.split(".")[-1]
                kind = "class" if last[:1].isupper() else "package"
                target = entity_id(kind, "java", "external", ref.name,
                                   disambiguator=ref.name)
                if target not in self.model.entities:
                    self.model.add_entity(target, kind,
                                          ref.name.split(".")[-1] if kind == "class" else ref.name,
                                          "extracted", [ev],
                                          qualified_name=ref.name, language="java",
                                          path=ref.path,
                                          attributes={"tool": "tree-sitter",
                                                      "external": True,
                                                      "import": ref.name})
                self.model.add_edge(ref.source_id, target, "imports", "extracted", [ev],
                                    attributes={"classification": "syntax"})

    # ---------- main ----------
    def build(self):
        all_java = sorted(self.repo.rglob("*.java"))
        generated = 0
        for path in all_java:
            rel = path.relative_to(self.repo).as_posix()
            if _excluded(rel):
                if "src/test" in rel or "/test/" in rel:
                    self.test_files += 1
                else:
                    generated += 1
                continue
            self.files.append(path)

        for path in self.files:
            rel = path.relative_to(self.repo).as_posix()
            try:
                source = path.read_bytes()
                tree = self.parser.parse(source)
                if tree.root_node.has_error:
                    self.skipped += 1
                    self.model.add_unknown(
                        f"tree-sitter reported parse errors in {rel}; syntax evidence may be incomplete.",
                        impact="medium", subject=None, owner="platform")
                    continue
                self.parsed += 1
                self._visit(tree.root_node, rel, Context(), None)
            except Exception as exc:
                self.skipped += 1
                self.model.add_unknown(f"Failed to parse {rel}: {exc}", impact="low",
                                       owner="platform")
        self._resolve_refs()

        if self.test_files:
            self.model.add_unknown(
                f"{self.test_files} test-source Java files were excluded from architecture evidence.",
                impact="low", owner="platform")
        if generated:
            self.model.add_unknown(
                f"{generated} generated/build-output Java files were excluded from architecture evidence.",
                impact="low", owner="platform")
        if self.unresolved_calls:
            self.model.add_unknown(
                f"{self.unresolved_calls} call/new sites could not be resolved by unique name and were not emitted.",
                impact="medium", owner="platform")
        entry_points = sum(1 for e in self.model.entities.values()
                           if e["kind"] == "method" and e["name"] == "main")
        return self.model, {
            "files_total": len(self.files),
            "files_analyzed": self.parsed,
            "files_skipped": self.skipped,
            "entry_points": entry_points,
            "data_stores": 0,
        }


def build(repo: str | Path, out_path: str | Path) -> dict:
    adapter = TreeSitterJavaAdapter(repo)
    model, coverage = adapter.build()
    return model.write(str(out_path), **coverage)
