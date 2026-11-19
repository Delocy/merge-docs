"""The API contract of each router module, built from code: endpoints plus request/response shapes."""
from __future__ import annotations

from dataclasses import dataclass

from merge_docs.core.extract import Field, extract_models, extract_routes, router_modules


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool


@dataclass(frozen=True)
class Shape:
    declared: bool
    model: str | None
    fields: tuple[FieldSpec, ...]
    many: bool = False  # a list of `model`, e.g. response_model=list[Order]

    @property
    def label(self) -> str:
        return f"list[{self.model}]" if self.many else str(self.model)


UNDECLARED = Shape(False, None, ())


@dataclass(frozen=True)
class EndpointContract:
    method: str
    path: str
    func: str
    request: Shape
    response: Shape

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class ModuleContract:
    module: str
    slug: str
    endpoints: tuple[EndpointContract, ...]


def slug_for(repo: str, module: str) -> str:
    return f"{repo.split('/')[-1]}/{module.removesuffix('.py')}"


def _shape(model: str | None, models: dict[str, list[Field]], many: bool = False) -> Shape:
    if not model or model not in models:
        return UNDECLARED
    fields: list[FieldSpec] = []
    for f in models[model]:
        fields.append(FieldSpec(f.name, f.display or f.type, f.required))
        if f.type in models and f.type != model:  # expand nested models one level
            fields += [FieldSpec(f"{f.name}.{n.name}", n.display or n.type, n.required) for n in models[f.type]]
    return Shape(True, model, tuple(fields), many)


def build_contracts(files: dict[str, str], repo: str) -> dict[str, ModuleContract]:
    models = extract_models(files)
    routes = extract_routes(files)
    out: dict[str, ModuleContract] = {}
    for module in router_modules(files):
        endpoints = tuple(
            EndpointContract(r.method, r.path, r.func, _shape(r.body_model, models), _shape(r.response_model, models, r.response_many))
            for r in routes if r.module == module
        )
        out[module] = ModuleContract(module, slug_for(repo, module), endpoints)
    return out
