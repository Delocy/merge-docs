"""Text the app shows people: the PR comment and a module's contract page (Markdown)."""
from __future__ import annotations

from itertools import groupby

from merge_docs.core.contract import ModuleContract, Shape
from merge_docs.core.deps import DepFinding
from merge_docs.core.diff import Change
from merge_docs.core.notes import notes_path

MARKER = "<!-- merge-docs:api-changes -->"
FOOTER = "_Read from the code by merge-docs. Check the notes and advisories above, if any._"


OSV_NOTE = "_OSV.dev could not be reached, so new dependencies were not checked for advisories._"


def _advisory_line(f: DepFinding) -> str:
    n = len(f.advisories)
    links = ", ".join(f"[{a}](https://osv.dev/vulnerability/{a})" for a in f.advisories[:3])
    more = f", +{n - 3} more" if n > 3 else ""
    return f"- `{f.dep.spec}` ({f.change}): {n} known advisor{'y' if n == 1 else 'ies'}: {links}{more}"


def render_comment(changes: list[Change], stale: dict[str, list[str]], had_changes_before: bool,
                   dep_findings: list[DepFinding] | None = None, osv_error: bool = False) -> str | None:
    dep_findings = dep_findings or []
    if not changes and not any(stale.values()) and not dep_findings:
        if not had_changes_before:
            return None
        note = f"\n\n{OSV_NOTE}" if osv_error else ""
        return f"{MARKER}\n### API changes\n\nNo API changes or dependency advisories in this PR any more.{note}\n\n{FOOTER}\n"

    lines = [MARKER, "### API changes in this PR" if changes or any(stale.values()) else "### Dependency check", ""]
    for module, group in groupby(sorted(changes, key=lambda c: c.module), key=lambda c: c.module):
        lines.append(f"**`{module}`**")
        lines += [f"- {c.detail}" if c.kind.startswith("endpoint") else f"- `{c.endpoint}`: {c.detail}" for c in group]
        lines.append("")
    notes = {m: s for m, s in stale.items() if s}
    if notes:
        lines.append("**Notes to update**")
        for module, items in sorted(notes.items()):
            lines += [f"- `{notes_path(module)}`: {item}" for item in items]
        lines.append("")
    if dep_findings:
        lines.append("**New or changed dependencies with known advisories (OSV.dev)**")
        lines += [_advisory_line(f) for f in sorted(dep_findings, key=lambda f: f.dep.name)]
        lines.append("")
    if osv_error:
        lines += [OSV_NOTE, ""]
    lines.append(FOOTER)
    return "\n".join(lines) + "\n"


def _table(shape: Shape) -> str:
    if not shape.declared:
        return "Not declared in the code."
    rows = ["| Field | Type | Required |", "|---|---|---|"]
    rows += [f"| `{f.name}` | {f.type.replace('|', chr(92) + '|')} | {'yes' if f.required else 'no'} |" for f in shape.fields]
    return f"Model `{shape.model}`\n\n" + "\n".join(rows) if shape.fields else f"Model `{shape.model}` (no fields)"


def render_module_markdown(contract: ModuleContract, notes: str | None) -> str:
    parts = [f"# {contract.slug}", f"Source: `{contract.module}`"]
    for e in contract.endpoints:
        parts += [f"## {e.key}", f"Handler: `{e.func}`", "**Request**", _table(e.request), "**Response**", _table(e.response)]
    parts.append("## Notes")
    parts.append(notes.strip() if notes else
                 f"No notes yet. Add `{notes_path(contract.module)}` to explain how this feature works.")
    return "\n\n".join(parts) + "\n"
