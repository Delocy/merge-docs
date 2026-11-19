"""Text the app shows people: the PR comment and a module's contract page (Markdown)."""
from __future__ import annotations

from itertools import groupby

from merge_docs.core.contract import ModuleContract, Shape
from merge_docs.core.diff import Change
from merge_docs.core.notes import notes_path

MARKER = "<!-- merge-docs:api-changes -->"
FOOTER = "_Read from the code by merge-docs. Nothing to do here unless notes are listed above._"


def render_comment(changes: list[Change], stale: dict[str, list[str]], had_changes_before: bool) -> str | None:
    if not changes and not any(stale.values()):
        if not had_changes_before:
            return None
        return f"{MARKER}\n### API changes\n\nNo API changes in this PR any more.\n\n{FOOTER}\n"

    lines = [MARKER, "### API changes in this PR", ""]
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
