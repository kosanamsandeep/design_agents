"""Reference canonicalization rules for evidence IDs.

Adapters must pass docs/canonicalization-fixtures.json. Qualified-name rules are
documented per language; this module implements the path and route rules that can
be shared across all adapters.
"""

from __future__ import annotations

import re
import unicodedata


def canonical_path(path: str) -> str:
    """Normalize a repository-relative path.

    - POSIX separators, NFC Unicode
    - no leading './', no leading '/'
    - collapse duplicate separators
    - no trailing slash (except the repository root '.')
    """
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
    if p == "":
        p = "."
    return p


_ROUTE_PARAM_BRACES = re.compile(r"\{[^}/]+\}")
_ROUTE_PARAM_COLON = re.compile(r"(?<=/):[^/]+")
_ROUTE_PARAM_ANGLE = re.compile(r"<[^/]+>")


def canonical_route(method: str, path: str) -> str:
    """Normalize an HTTP route.

    - method lower-case
    - strip query string and fragment
    - collapse duplicate slashes, ensure a leading slash
    - no trailing slash except root
    - normalize every path parameter to '{param}' (names belong in attributes)
    """
    if not isinstance(method, str) or not method:
        raise ValueError("method must be a non-empty string")
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
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


def canonical_qualified_name(language: str, module: str, name: str,
                             parameter_types: list[str] | None = None) -> str:
    """Return the documented qualified-name form for a language.

    Overloads must be distinguishable. When parameter types are supplied, append a
    short stable hash so two overloads do not collapse into one identity.
    """
    lang = language.lower()
    if lang == "python":
        return f"{module}.{name}" if module else name
    if lang in ("java", "kotlin", "scala"):
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
        import hashlib
        digest = hashlib.sha256(",".join(parameter_types).encode("utf-8")).hexdigest()[:8]
        return f"{base}@{digest}"
    return base
