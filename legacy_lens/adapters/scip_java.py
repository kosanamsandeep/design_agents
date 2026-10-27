"""SCIP Java adapter: index.scip -> evidence model.

SCIP gives compiler-accurate definitions and references. We create entities for
defined symbols and edges for references. The edge kind is inferred from the
referenced symbol kind (method/function -> calls, import role -> imports,
otherwise uses), so call edges are marked `inferred`; the evidence is extracted.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..canonical import entity_id, short_hash
from ..gitinfo import commit
from ..java_scopes import collect_scopes, find_scope
from ..model import Model, evidence, span
from ..proto import scip_pb2

KIND_MAP = {
    "Class": "class",
    "Struct": "class",
    "Object": "class",
    "Interface": "interface",
    "Trait": "interface",
    "Enum": "enum",
    "Method": "method",
    "StaticMethod": "method",
    "AbstractMethod": "method",
    "Constructor": "method",
    "Getter": "method",
    "Setter": "method",
    "Accessor": "method",
    "Operator": "method",
    "ProtocolMethod": "method",
    "TraitMethod": "method",
    "TypeClassMethod": "method",
    "MethodAlias": "method",
    "Function": "function",
    "Module": "module",
    "Namespace": "module",
    "Package": "package",
    "PackageObject": "package",
    "File": "file",
    "Field": "field",
    "StaticField": "field",
    "StaticDataMember": "field",
    "Property": "property",
    "StaticProperty": "property",
    "Attribute": "property",
}

def _is_test_path(path: str) -> bool:
    if "src/test" in path or "/test/" in path:
        return True
    parts = path.split("/")
    return any(p in ("target", "build", "out", "generated-sources",
                     "generated-test-sources", ".git") for p in parts)


DEFINITION = 1
IMPORT = 2
FORWARD_DEFINITION = 64


def _range(occ) -> tuple[tuple[int, int], tuple[int, int]] | None:
    r = list(occ.range)
    if len(r) == 3:
        return (r[0], r[1]), (r[0], r[2])
    if len(r) == 4:
        return (r[0], r[1]), (r[2], r[3])
    if occ.HasField("single_line_range"):
        s = occ.single_line_range
        return (s.line, s.start_character), (s.line, s.end_character)
    if occ.HasField("multi_line_range"):
        m = occ.multi_line_range
        return (m.start_line, m.start_character), (m.end_line, m.end_character)
    return None


def _span(occ) -> dict | None:
    rng = _range(occ)
    if not rng:
        return None
    (sl, sc), (el, ec) = rng
    return span(sl, el, sc, ec, one_based=False)


def _kind(info) -> str | None:
    if info is None:
        return None
    try:
        name = scip_pb2.SymbolInformation.Kind.Name(info.kind)
    except Exception:
        return None
    return KIND_MAP.get(name)


def _clean_name(info, symbol: str) -> str:
    name = (getattr(info, "display_name", "") or "").strip()
    if not name:
        tail = symbol.split()[-1] if " " in symbol else symbol
        tail = tail.split("/")[-1].split("#")[-1]
        name = tail.strip("().$[]")
    name = re.sub(r"\([^)]*\)$", "", name)      # setName(+1) -> setName
    name = re.sub(r"\[[^\]]*\]$", "", name)
    return name.strip() or "unknown"


def _package_from_path(path: str) -> str:
    m = re.search(r"src/(?:main|test)/java/(.*)/[^/]+\.java$", path)
    return m.group(1).replace("/", ".") if m else ""


class ScipJavaAdapter:
    def __init__(self, repo: str | Path, index_path: str | Path,
                 include_external: bool = True, include_files: bool = True,
                 edge_kinds: set[str] | None = None, include_tests: bool = False):
        self.repo = Path(repo)
        self.index_path = Path(index_path)
        self.index = scip_pb2.Index()
        self.index.ParseFromString(self.index_path.read_bytes())
        raw_version = self.index.metadata.tool_info.version or ""
        self.tool_version = "0.13.2" if raw_version in ("", "0.0.0-SNAPSHOT") else raw_version
        self.commit = commit(self.repo)
        self.model = Model(
            commit=self.commit,
            root=str(self.repo.resolve()),
            languages=["java"],
            tool_versions={"scip-java": self.tool_version},
        )
        self.info: dict[str, object] = {}
        for sym in self.index.external_symbols:
            self.info[sym.symbol] = sym
        for doc in self.index.documents:
            for sym in doc.symbols:
                self.info[sym.symbol] = sym
        self.symbol_to_id: dict[str, str] = {}
        self.base_ids: dict[str, str] = {}
        self.doc_defs: dict[str, list[tuple[tuple[int, int], tuple[int, int], str]]] = {}
        self.file_ids: dict[str, str] = {}
        self.external_count = 0
        self.skipped_kinds: dict[str, int] = {}
        self.qname_to_symbol: dict[str, str] = {}
        self.qname_to_id: dict[str, str] = {}
        self.include_external = include_external
        self.include_files = include_files
        self.edge_kinds = edge_kinds
        self.documents = [d for d in self.index.documents
                          if include_tests or not _is_test_path(d.relative_path)]

    # ---------- IDs ----------
    def _assign_id(self, kind: str, path: str, qname: str, symbol: str) -> str:
        base = entity_id(kind, "java", path, qname)
        owner = self.base_ids.get(base)
        if owner is None or owner == symbol:
            self.base_ids[base] = symbol
            return base
        return f"{base}@{short_hash(symbol)}"

    def _qname(self, info, name: str, kind: str, package: str) -> str:
        parent_symbol = getattr(info, "enclosing_symbol", "") if info else ""
        parent_info = self.info.get(parent_symbol) if parent_symbol else None
        parent_kind = _kind(parent_info)
        if parent_info is not None and parent_kind in ("class", "interface", "enum"):
            parent_name = _clean_name(parent_info, parent_symbol)
            parent_qname = self._qname(parent_info, parent_name, parent_kind, package)
            sep = "#" if kind in ("method", "field", "property") else "."
            return f"{parent_qname}{sep}{name}"
        return f"{package}.{name}" if package else name

    def _entity_for_definition(self, doc, occ, info, scopes) -> str | None:
        symbol = occ.symbol
        if not symbol:
            return None
        kind = _kind(info)
        if kind == "file" and not self.include_files:
            return None
        if kind is None:
            try:
                kname = scip_pb2.SymbolInformation.Kind.Name(info.kind) if info else "UnspecifiedKind"
            except Exception:
                kname = "UnspecifiedKind"
            self.skipped_kinds[kname] = self.skipped_kinds.get(kname, 0) + 1
            return None
        name = _clean_name(info, symbol)
        parent_symbol = getattr(info, "enclosing_symbol", "") if info else ""
        parent_info = self.info.get(parent_symbol) if parent_symbol else None
        if name == "<init>" and parent_info is not None:
            name = _clean_name(parent_info, parent_symbol)
        if name == "<clinit>":
            return None
        parent_id = self.symbol_to_id.get(parent_symbol) if parent_symbol else None
        rng = _range(occ)
        scope_qname = find_scope(scopes.get(doc.relative_path, []), rng[0][0], rng[0][1]) if rng else None
        if scope_qname and kind in ("method", "function") and "#" in scope_qname:
            scope_method = scope_qname.rsplit("#", 1)[-1]
            if scope_method:
                name = scope_method
        if kind in ("method", "function") and name in ("call", "<lambda>", "lambda") and not scope_qname:
            return None
        if scope_qname:
            if kind in ("method", "function") and "#" not in scope_qname:
                qname = f"{scope_qname}#{name}"
            elif kind in ("field", "property") and "#" not in scope_qname:
                qname = f"{scope_qname}#{name}"
            else:
                qname = scope_qname
        else:
            package = _package_from_path(doc.relative_path)
            qname = self._qname(info, name, kind, package)
        eid = self._assign_id(kind, doc.relative_path, qname, symbol)
        sp = _span(occ)
        ev = evidence("scip-java", self.tool_version, "source_span",
                      doc.relative_path, self.commit, sp,
                      extractor="scip-index")
        self.model.add_entity(
            eid, kind, name, "extracted", [ev],
            qualified_name=qname, language="java",
            path=doc.relative_path, span_obj=sp, parent_id=parent_id,
            attributes={"scip_symbol": symbol, "tool": "scip-java"},
        )
        self.symbol_to_id[symbol] = eid
        if qname not in self.qname_to_symbol:
            self.qname_to_symbol[qname] = symbol
        self.qname_to_id.setdefault(qname, eid)
        return eid

    def _entity_for_external(self, symbol: str, doc, occ) -> str | None:
        if symbol in self.symbol_to_id:
            return self.symbol_to_id[symbol]
        if not self.include_external:
            return None
        if re.match(r"^(local|parameter)\b", symbol):
            return None
        info = self.info.get(symbol)
        kind = _kind(info) or "external_system"
        name = _clean_name(info, symbol)
        eid = entity_id(kind, "java", "external", name, disambiguator=symbol)
        sp = _span(occ)
        ev = evidence("scip-java", self.tool_version, "source_span",
                      doc.relative_path, self.commit, sp,
                      extractor="scip-reference",
                      note="External symbol observed by reference only.")
        self.model.add_entity(
            eid, kind, name, "extracted", [ev],
            qualified_name=name, language="java",
            path=doc.relative_path, span_obj=sp,
            attributes={"scip_symbol": symbol, "external": True, "tool": "scip-java"},
        )
        self.symbol_to_id[symbol] = eid
        self.external_count += 1
        return eid

    def _file_entity(self, doc) -> str | None:
        if not self.include_files:
            return None
        path = doc.relative_path
        if path in self.file_ids:
            return self.file_ids[path]
        eid = entity_id("file", "java", path, Path(path).name)
        ev = evidence("scip-java", self.tool_version, "source_span", path,
                      self.commit, span(1, 1), extractor="scip-document")
        self.model.add_entity(
            eid, "file", Path(path).name, "extracted", [ev],
            qualified_name=path, language="java", path=path,
            span_obj=span(1, 1),
            attributes={"tool": "scip-java"},
        )
        self.file_ids[path] = eid
        return eid

    def _source_for(self, doc, occ) -> str | None:
        rng = _range(occ)
        if not rng:
            return None
        start = rng[0]
        defs = self.doc_defs.get(doc.relative_path, [])
        best = None
        for d_start, d_end, symbol in defs:
            if d_start <= start <= d_end:
                if best is None or d_start >= best[0]:
                    best = (d_start, d_end, symbol)
        if best is None:
            return None
        return self.symbol_to_id.get(best[2])

    # ---------- main ----------
    def build(self) -> Model:
        scopes = collect_scopes(
            self.repo,
            [d.relative_path for d in self.documents if d.relative_path],
        )

        # Pass 1: definition entities, then parent links.
        definitions = []
        for doc in self.documents:
            defs = []
            for occ in doc.occurrences:
                if not occ.symbol:
                    continue
                if occ.symbol_roles & (DEFINITION | FORWARD_DEFINITION):
                    definitions.append((doc, occ))
                    rng = _range(occ)
                    if rng:
                        defs.append((rng[0], rng[1], occ.symbol))
            defs.sort(key=lambda d: (d[0], d[1]))
            self.doc_defs[doc.relative_path] = defs

        for doc, occ in definitions:
            info = self.info.get(occ.symbol)
            self._entity_for_definition(doc, occ, info, scopes)

        for doc, occ in definitions:
            eid = self.symbol_to_id.get(occ.symbol)
            info = self.info.get(occ.symbol)
            if not eid or not info:
                continue
            parent_symbol = getattr(info, "enclosing_symbol", "")
            parent_id = self.symbol_to_id.get(parent_symbol) if parent_symbol else None
            if parent_id and eid in self.model.entities:
                self.model.entities[eid]["parent_id"] = parent_id

        # Parent links from qualified names.
        for eid, ent in self.model.entities.items():
            q = ent.get("qualified_name") or ""
            if "#" in q:
                parent_q = q.split("#", 1)[0]
            elif "." in q:
                parent_q = q.rsplit(".", 1)[0]
            else:
                continue
            pid = self.qname_to_id.get(parent_q)
            if pid:
                ent["parent_id"] = pid

        # Pass 2: reference edges.
        for doc in self.documents:
            for occ in doc.occurrences:
                if not occ.symbol:
                    continue
                if occ.symbol_roles & (DEFINITION | FORWARD_DEFINITION):
                    continue
                target = self._entity_for_external(occ.symbol, doc, occ)
                if target is None:
                    continue
                source = self._source_for(doc, occ)
                if source is None:
                    rng = _range(occ)
                    if rng:
                        qname = find_scope(
                            scopes.get(doc.relative_path, []),
                            rng[0][0], rng[0][1],
                        )
                        if qname:
                            source = self.symbol_to_id.get(self.qname_to_symbol.get(qname, ""))
                outside_definition = source is None
                if outside_definition:
                    source = self._file_entity(doc)
                target_info = self.info.get(occ.symbol)
                target_kind = _kind(target_info)
                if (occ.symbol_roles & IMPORT) or outside_definition:
                    edge_kind, confidence = "imports", "extracted"
                elif target_kind in ("method", "function"):
                    edge_kind, confidence = "calls", "inferred"
                else:
                    edge_kind, confidence = "uses", "extracted"
                sp = _span(occ)
                ev = evidence("scip-java", self.tool_version, "source_span",
                              doc.relative_path, self.commit, sp,
                              extractor="scip-occurrence")
                if self.edge_kinds is not None and edge_kind not in self.edge_kinds:
                    continue
                self.model.add_edge(
                    source, target, edge_kind, confidence, [ev],
                    attributes={"classification": "scip-symbol-kind"},
                )

        analyzed = sum(1 for d in self.documents if d.occurrences or d.symbols)
        total = len(self.documents)
        entry_points = sum(
            1 for e in self.model.entities.values()
            if e["kind"] == "method" and e["name"] == "main"
        )
        if self.external_count:
            self.model.add_unknown(
                f"{self.external_count} external symbols are observed only at reference sites; their definitions are outside the indexed repository.",
                impact="low", owner="platform", evidence_items=None,
            )
        if self.skipped_kinds:
            self.model.add_unknown(
                "SCIP symbol kinds not mapped to the evidence model: " +
                ", ".join(f"{k} ({v})" for k, v in sorted(self.skipped_kinds.items())),
                impact="medium", owner="platform",
            )
        return self.model, {
            "files_total": total,
            "files_analyzed": analyzed,
            "files_skipped": total - analyzed,
            "entry_points": entry_points,
            "data_stores": 0,
        }


def build(repo: str | Path, index_path: str | Path, out_path: str | Path,
          include_external: bool = True, include_files: bool = True,
          edge_kinds: set[str] | None = None, include_tests: bool = False) -> dict:
    adapter = ScipJavaAdapter(repo, index_path, include_external=include_external,
                              include_files=include_files, edge_kinds=edge_kinds,
                              include_tests=include_tests)
    model, coverage = adapter.build()
    return model.write(str(out_path), **coverage)
