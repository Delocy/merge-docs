"""Optional author notes per module, and a check for mentions the code no longer backs up."""
from __future__ import annotations

import re

from merge_docs.core.contract import ModuleContract

_ENDPOINT = re.compile(r"^(GET|POST|PUT|PATCH|DELETE) (/\S*)$")
_FIELD = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")
_PARAM = re.compile(r"\{[^}]*\}")
_SPAN = re.compile(r"`([^`\n]+)`")


def notes_path(module: str) -> str:
    return "docs/features/" + module.removesuffix(".py") + ".md"


def _prose(note_md: str) -> str:
    """The note without fenced code blocks."""
    out, fence = [], None
    for line in note_md.split("\n"):
        marker = "~~~" if line.startswith("~~~") else "```" if line.startswith("```") else None
        if marker:
            fence = None if fence == marker else (fence or marker)
            continue
        if fence is None:
            out.append(line)
    return "\n".join(out)


def mentions(note_md: str) -> tuple[set[str], set[str]]:
    endpoints, fields = set(), set()
    for span in _SPAN.findall(_prose(note_md)):
        span = span.strip()
        if _ENDPOINT.match(span):
            endpoints.add(span)
        elif _FIELD.match(span):
            fields.add(span)
    return endpoints, fields


def _norm(key: str) -> str:
    method, _, path = key.partition(" ")
    return f"{method} {_PARAM.sub('{}', path.rstrip('/') or '/')}"


def _endpoints(contracts: dict[str, ModuleContract]) -> set[str]:
    return {_norm(e.key) for c in contracts.values() for e in c.endpoints}


def _fields(contracts: dict[str, ModuleContract]) -> set[str]:
    return {f.name for c in contracts.values() for e in c.endpoints for s in (e.request, e.response) for f in s.fields}


def stale_mentions(note_md: str, new: dict[str, ModuleContract], old: dict[str, ModuleContract] | None) -> list[str]:
    """Mentions that this change made stale: they matched something before and match nothing now.

    Both snapshots are whole-repo, so a note may mention another module's endpoints. A mention that
    never matched (an old typo, a backticked word like `json`) is never reported. Without `old`,
    nothing is judged.
    """
    if old is None:
        return []
    endpoints, fields = mentions(note_md)
    gone_endpoints = _endpoints(old) - _endpoints(new)
    gone_fields = _fields(old) - _fields(new)
    out = [f"`{m}` no longer exists" for m in sorted(endpoints) if _norm(m) in gone_endpoints]
    out += [f"`{m}` no longer exists" for m in sorted(fields) if m in gone_fields]
    return out
