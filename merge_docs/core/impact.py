"""Which router modules a change affects."""
from __future__ import annotations

from merge_docs.core.extract import (classes_defined, extract_routes, model_dependencies, mounted_modules,
                                     router_modules)


def touched_modules(changed: list[str], files: dict[str, str]) -> list[str]:
    """Router modules a PR affects: edited directly, re-mounted by a changed include_router, or using a
    model (directly, through a base class, or through a nested field type) defined in a changed file."""
    routers = router_modules(files)
    changed_py = {c for c in changed if c.endswith(".py") and c in files}
    deps = model_dependencies(files)
    changed_models = classes_defined({p: files[p] for p in changed_py}) & set(deps)
    mounted = set().union(*(mounted_modules(files, p) for p in changed_py)) if changed_py else set()
    routes = extract_routes(files)

    def closure(names: set[str]) -> set[str]:
        seen, queue = set(), list(names)
        while queue:
            n = queue.pop()
            if n in seen or n not in deps:
                continue
            seen.add(n)
            queue.extend(deps[n])
        return seen

    out = []
    for module in routers:
        used = {m for r in routes if r.module == module for m in (r.body_model, r.response_model) if m}
        if module in changed_py or module in mounted or closure(used) & changed_models:
            out.append(module)
    return out
