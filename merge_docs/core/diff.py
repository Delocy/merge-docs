"""What changed in the API contract between two snapshots (a PR's base and head)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from merge_docs.core.contract import EndpointContract, FieldSpec, ModuleContract, Shape

Kind = Literal["endpoint_added", "endpoint_removed", "endpoint_renamed", "field_added", "field_removed",
               "field_retyped", "field_required_changed", "shape_declared", "shape_undeclared"]

_PARAM = re.compile(r"\{[^}]*\}")


@dataclass(frozen=True)
class Change:
    module: str
    kind: Kind
    endpoint: str
    detail: str


def _norm(e: EndpointContract) -> tuple[str, str]:
    return e.method, _PARAM.sub("{}", e.path.rstrip("/") or "/")


def _req(f: FieldSpec) -> str:
    return "required" if f.required else "optional"


def _shape_changes(module: str, endpoint: str, side: str, old: Shape, new: Shape) -> list[Change]:
    if old.declared and not new.declared:
        return [Change(module, "shape_undeclared", endpoint, f"{side} no longer declares a model (was {old.model})")]
    if new.declared and not old.declared:
        return [Change(module, "shape_declared", endpoint, f"{side} now declares {new.model}")]
    if not new.declared:
        return []
    out: list[Change] = []
    if old.many != new.many or old.model != new.model:
        out.append(Change(module, "field_retyped", endpoint, f"{side} changed from {old.label} to {new.label}"))
    before = {f.name: f for f in old.fields}
    after = {f.name: f for f in new.fields}
    for name in sorted(after.keys() - before.keys()):
        f = after[name]
        out.append(Change(module, "field_added", endpoint, f"{side} field `{name}` added ({f.type}, {_req(f)})"))
    for name in sorted(before.keys() - after.keys()):
        out.append(Change(module, "field_removed", endpoint, f"{side} field `{name}` removed"))
    for name in sorted(before.keys() & after.keys()):
        b, a = before[name], after[name]
        if b.type != a.type:
            out.append(Change(module, "field_retyped", endpoint, f"{side} field `{name}` changed type: {b.type} → {a.type}"))
        if b.required != a.required:
            out.append(Change(module, "field_required_changed", endpoint,
                              f"{side} field `{name}` is now {_req(a)} (was {_req(b)})"))
    return out


def _endpoint_changes(module: str, old: EndpointContract, new: EndpointContract) -> list[Change]:
    return (_shape_changes(module, new.key, "request", old.request, new.request)
            + _shape_changes(module, new.key, "response", old.response, new.response))


def _module_changes(module: str, old: ModuleContract | None, new: ModuleContract | None) -> list[Change]:
    before = {_norm(e): e for e in (old.endpoints if old else ())}
    after = {_norm(e): e for e in (new.endpoints if new else ())}
    out: list[Change] = []
    for k in before.keys() & after.keys():
        out += _endpoint_changes(module, before[k], after[k])

    removed = {k: before[k] for k in before.keys() - after.keys()}
    added = {k: after[k] for k in after.keys() - before.keys()}
    by_func = {}
    for k, e in added.items():
        by_func.setdefault(e.func, []).append(k)
    for k, old_e in sorted(removed.items()):
        candidates = by_func.get(old_e.func, [])
        if len(candidates) == 1 and candidates[0] in added:
            new_e = added.pop(candidates[0])
            out.append(Change(module, "endpoint_renamed", new_e.key, f"{old_e.key} is now {new_e.key}"))
            out += _endpoint_changes(module, old_e, new_e)
        else:
            out.append(Change(module, "endpoint_removed", old_e.key, f"{old_e.key} removed"))
    for e in added.values():
        out.append(Change(module, "endpoint_added", e.key, f"{e.key} added"))
    return out


def diff_contracts(old: dict[str, ModuleContract], new: dict[str, ModuleContract]) -> list[Change]:
    changes: list[Change] = []
    for module in old.keys() | new.keys():
        changes += _module_changes(module, old.get(module), new.get(module))
    order = {k: i for i, k in enumerate(Kind.__args__)}
    return sorted(changes, key=lambda c: (c.module, c.endpoint, order[c.kind], c.detail))
