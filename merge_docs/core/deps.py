"""Read a repo's Python dependencies (requirements.txt, pyproject.toml) for the Dependencies page.

Only the names and exact pins are read here; the page looks each package up on PyPI and OSV.dev in
the browser.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass

_REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
_PIN = re.compile(r"^==\s*([^\s,*;]+)$")


@dataclass(frozen=True)
class Dependency:
    name: str  # normalised (PEP 503): lower case, runs of -_. become -
    version: str | None  # the exact pinned version, or None if not pinned with ==
    spec: str  # the requirement as written, without markers or comments
    source: str  # the file it came from


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse(line: str, source: str) -> Dependency | None:
    line = line.split(" #", 1)[0].split(";", 1)[0].strip()
    if not line or line.startswith(("#", "-")) or "://" in line or line.startswith("git+"):
        return None
    m = _REQ.match(line)
    if not m:
        return None
    name, extras, spec = m.group(1), m.group(2) or "", m.group(3).strip()
    pin = _PIN.match(spec)
    return Dependency(_normalise(name), pin.group(1) if pin else None, f"{name}{extras}{spec}", source)


def read_dependencies(files: dict[str, str]) -> list[Dependency]:
    found: dict[str, Dependency] = {}
    if "requirements.txt" in files:
        for line in files["requirements.txt"].splitlines():
            dep = _parse(line, "requirements.txt")
            if dep and dep.name not in found:
                found[dep.name] = dep
    if "pyproject.toml" in files:
        try:
            project = tomllib.loads(files["pyproject.toml"]).get("project", {})
        except tomllib.TOMLDecodeError:
            project = {}
        for line in project.get("dependencies", []) or []:
            dep = _parse(str(line), "pyproject.toml")
            if dep and dep.name not in found:  # an exact pin in requirements.txt wins
                found[dep.name] = dep
    return sorted(found.values(), key=lambda d: d.name)


@dataclass(frozen=True)
class DepFinding:
    dep: Dependency
    change: str  # "added", "changed from 1.2.3", or "newly pinned"
    advisories: tuple[str, ...]  # OSV ids


def changed_dependencies(old: list[Dependency], new: list[Dependency]) -> list[tuple[Dependency, str]]:
    """Pinned dependencies a change adds or re-pins. Only these have an exact version to check."""
    before = {d.name: d for d in old}
    out = []
    for d in new:
        if d.version is None:
            continue
        prev = before.get(d.name)
        if prev is None:
            out.append((d, "added"))
        elif prev.version != d.version:
            out.append((d, f"changed from {prev.version}" if prev.version else "newly pinned"))
    return out
