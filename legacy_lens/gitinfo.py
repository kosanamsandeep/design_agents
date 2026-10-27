"""Repository facts used by the adapters."""

from __future__ import annotations

import subprocess
from pathlib import Path

EXCLUDED_DIRS = {".git", "target", "build", "out", ".idea", ".gradle", "node_modules"}


def run_git(repo: str | Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def commit(repo: str | Path) -> str:
    # A vendored test snapshot has no .git; the marker is authoritative.
    marker = Path(repo) / ".lens-commit"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return run_git(repo, "rev-parse", "HEAD")


def repo_root(repo: str | Path) -> str:
    if (Path(repo) / ".lens-commit").exists():
        return str(Path(repo).resolve())
    try:
        return run_git(repo, "rev-parse", "--show-toplevel")
    except Exception:
        return str(Path(repo).resolve())


def java_files(repo: str | Path, include_tests: bool = False) -> list[Path]:
    root = Path(repo)
    files: list[Path] = []
    for path in root.rglob("*.java"):
        rel = path.relative_to(root).as_posix()
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not include_tests and ("src/test" in rel or "/test/" in rel):
            continue
        files.append(path)
    return sorted(files)


def tool_version(command: list[str], fallback: str = "unknown") -> str:
    try:
        out = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
        return out.splitlines()[0] if out else fallback
    except Exception:
        return fallback
