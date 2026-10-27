"""Canonical IDs and paths for the evidence model.

Mirrors docs/canonicalize.py so adapters and the reference fixtures agree.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


def canonical_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    p = path.replace("\\", "/")
    p = unicodedata.normalize("NFC", p)
    p = re.sub(r"/{2,}", "/", p)
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    if p not in ("", "."):
        p = p.rstrip("/")
    return p or "."


_ROUTE_PARAM_BRACES = re.compile(r"\{[^}/]+\}")
_ROUTE_PARAM_COLON = re.compile(r"(?<=/):[^/]+")
_ROUTE_PARAM_ANGLE = re.compile(r"<[^/]+>")


def canonical_route(method: str, path: str) -> str:
    p = path.split("?", 1)[0].split("#", 1)[0]
    p = re.sub(r"/{2,}", "/", p)
    if not p.startswith("/"):
        p = "/" + p
    if p != "/":
        p = p.rstrip("/")
    p = _ROUTE_PARAM_BRACES.sub("{param}", p)
    p = _ROUTE_PARAM_COLON.sub("{param}", p)
    p = _ROUTE_PARAM_ANGLE.sub("{param}", p)
    return f"route:{method.lower()}:{p}"


def short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def slug(value: str, max_len: int = 120) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    value = re.sub(r"\s+", " ", value)
    value = value.replace("#", ".").replace("::", ".")
    value = re.sub(r"[^A-Za-z0-9_.$<>{}()\[\],@-]+", "_", value)
    value = value.strip("._")
    return (value or "anonymous")[:max_len]


def entity_id(kind: str, language: str, path: str | None, name: str,
              disambiguator: str | None = None) -> str:
    """Build a stable, readable ID.

    A disambiguator (e.g. the SCIP symbol) is hashed and appended only when the
    caller needs to distinguish overloads or same-named nested entities.
    """
    if not re.fullmatch(r"[a-z_]+", kind):
        raise ValueError(f"kind must be lowercase snake_case: {kind!r}")
    language = (language or "unknown").lower()
    where = canonical_path(path) if path else "external"
    base = f"{kind}:{language}:{where}#{slug(name)}"
    if disambiguator:
        base += f"@{short_hash(disambiguator)}"
    return base


def canonical_qualified_name(language: str, module: str, name: str,
                             parameter_types: list[str] | None = None) -> str:
    lang = (language or "").lower()
    if lang == "python":
        base = f"{module}.{name}" if module else name
    elif lang in ("java", "kotlin", "scala"):
        base = f"{module}.{name}" if module else name
    elif lang in ("typescript", "javascript"):
        base = f"{module}#{name}" if module else name
    elif lang == "go":
        base = f"{module}.{name}" if module else name
    elif lang == "csharp":
        base = f"{module}.{name}" if module else name
    else:
        base = f"{module}:{name}" if module else name
    if parameter_types:
        base += f"@{short_hash(','.join(parameter_types))}"
    return base
