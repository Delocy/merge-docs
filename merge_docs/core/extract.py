"""Read FastAPI routes and Pydantic models from source code, without importing it.

Everything here works on a mapping of repo path -> source text and uses `ast` only,
so code that would fail (or do something) on import is never run.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
CONTAINERS = {"List", "list", "Sequence", "Set", "set", "FrozenSet", "frozenset", "Tuple", "tuple", "Iterable"}
TEST_PATH = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$")
PRIMITIVES = {"int", "str", "float", "bool", "bytes", "dict", "Dict", "Any", "None"}


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    module: str
    func: str
    body_model: str | None
    response_model: str | None
    response_many: bool = False  # response_model=list[X]


@dataclass(frozen=True)
class Field:
    name: str
    type: str  # core type name, e.g. "Item" for list[Item] | None; used to look up models
    required: bool
    display: str = ""  # the full type as callers see it, e.g. "list[Item] | None"


# ---------- helpers ----------

def _parse(files: dict[str, str]) -> dict[str, ast.Module]:
    trees = {}
    for path, src in files.items():
        if not path.endswith(".py") or TEST_PATH.search(path):
            continue
        try:
            trees[path] = ast.parse(src, filename=path)
        except SyntaxError:
            continue
    return trees


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def unwrap_type(node: ast.AST | None) -> str | None:
    """Reduce an annotation to its core type name: Optional[X], list[X], X | None -> X."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return unwrap_type(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts = [p for p in (unwrap_type(node.left), unwrap_type(node.right)) if p and p != "None"]
        return parts[0] if len(parts) == 1 else " | ".join(parts) if parts else "None"
    if isinstance(node, ast.Subscript):
        outer = unwrap_type(node.value)
        inner = node.slice
        if outer == "Optional" or outer in CONTAINERS:
            if isinstance(inner, ast.Tuple):  # tuple[X, ...]
                inner = inner.elts[0]
            return unwrap_type(inner)
        if outer == "Union" and isinstance(inner, ast.Tuple):
            parts = [p for p in (unwrap_type(e) for e in inner.elts) if p and p != "None"]
            return parts[0] if len(parts) == 1 else " | ".join(parts)
        if outer == "Annotated":
            first = inner.elts[0] if isinstance(inner, ast.Tuple) else inner
            return unwrap_type(first)
        return ast.unparse(node)
    if isinstance(node, ast.Constant) and node.value is None:
        return "None"
    return ast.unparse(node)


_LIST_LIKE = {"List": "list", "list": "list", "Sequence": "list", "Iterable": "list", "Set": "set", "set": "set",
              "FrozenSet": "frozenset", "frozenset": "frozenset", "Tuple": "tuple", "tuple": "tuple",
              "Dict": "dict", "dict": "dict"}


def display_type(node: ast.AST | None) -> str:
    """The full type, normalised so Optional[X] == X | None and List[X] == list[X]."""
    if node is None:
        return "Any"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return display_type(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return node.value
    if isinstance(node, ast.Constant) and node.value is None:
        return "None"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _union([display_type(node.left), display_type(node.right)])
    if isinstance(node, ast.Subscript):
        outer = unwrap_type(node.value) if not isinstance(node.value, ast.Subscript) else ast.unparse(node.value)
        args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if outer == "Optional":
            return _union([display_type(args[0]), "None"])
        if outer == "Union":
            return _union([display_type(a) for a in args])
        if outer == "Annotated":
            return display_type(args[0])
        name = _LIST_LIKE.get(outer, outer)
        return f"{name}[{', '.join(display_type(a) for a in args)}]"
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ast.unparse(node)


def _union(parts: list[str]) -> str:
    flat: list[str] = []
    for p in parts:
        for q in p.split(" | "):
            if q not in flat:
                flat.append(q)
    flat.sort(key=lambda t: (t == "None", t))
    return " | ".join(flat)


def is_many(node: ast.AST | None) -> bool:
    """True for list[X], List[X], Sequence[X] (also inside Optional/Annotated)."""
    if isinstance(node, ast.Subscript):
        outer = unwrap_type(node.value)
        args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if outer in ("Optional", "Annotated"):
            return is_many(args[0])
        return _LIST_LIKE.get(outer) in ("list", "set", "frozenset", "tuple")
    return False


def _module_file(dotted: str, trees: dict[str, ast.Module]) -> str | None:
    base = dotted.replace(".", "/")
    for candidate in (base + ".py", base + "/__init__.py"):
        if candidate in trees:
            return candidate
    # tolerate a repo where the package root sits below the file keys (e.g. src/app/...)
    for path in trees:
        if path.endswith("/" + base + ".py"):
            return path
    return None


def _import_aliases(tree: ast.Module, path: str, trees: dict[str, ast.Module]) -> dict[str, tuple[str, str | None]]:
    """alias -> (file, attribute or None). `from a.b import c` -> c: (a/b/c.py, None) or (a/b.py, 'c')."""
    out: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or node.level):
            if node.level:
                package = path.split("/")[:-1]
                package = package[: len(package) - (node.level - 1)] if node.level > 1 else package
                base = ".".join(package + (node.module.split(".") if node.module else []))
            else:
                base = node.module
            for a in node.names:
                alias = a.asname or a.name
                as_module = _module_file(f"{base}.{a.name}" if base else a.name, trees)
                if as_module:
                    out[alias] = (as_module, None)
                else:
                    owner = _module_file(base, trees) if base else None
                    if owner:
                        out[alias] = (owner, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                f = _module_file(a.name, trees)
                if f:
                    out[a.asname or a.name] = (f, None)
    return out


# ---------- routers and prefixes ----------

def _router_vars(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """var name -> (kind 'router'|'app', own prefix)."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target, value = node.target.id, node.value
        else:
            continue
        name = _call_name(value)
        if name == "APIRouter":
            out[target] = ("router", _str(_kw(value, "prefix")) or "")
        elif name == "FastAPI":
            out.setdefault(target, ("app", ""))
    return out


def router_modules(files: dict[str, str]) -> list[str]:
    trees = _parse(files)
    return sorted(p for p, t in trees.items() if any(k == "router" for k, _ in _router_vars(t).values()))


def _include_prefixes(trees: dict[str, ast.Module]) -> dict[tuple[str, str], str]:
    """(file, router var) -> prefix contributed by include_router calls (resolved through parents)."""
    edges: dict[tuple[str, str], tuple[tuple[str, str], str]] = {}
    for path, tree in trees.items():
        aliases = _import_aliases(tree, path, trees)
        local = _router_vars(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router"):
                continue
            parent = node.func.value
            if not (isinstance(parent, ast.Name) and parent.id in local):
                continue
            if not node.args:
                continue
            arg = node.args[0]
            child: tuple[str, str] | None = None
            if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                target = aliases.get(arg.value.id)
                if target and target[1] is None:
                    child = (target[0], arg.attr)
            elif isinstance(arg, ast.Name):
                if arg.id in local:
                    child = (path, arg.id)
                elif arg.id in aliases and aliases[arg.id][1]:
                    child = (aliases[arg.id][0], aliases[arg.id][1])
            if child:
                edges.setdefault(child, ((path, parent.id), _str(_kw(node, "prefix")) or ""))

    resolved: dict[tuple[str, str], str] = {}

    def resolve(key, seen=()):
        if key in resolved:
            return resolved[key]
        if key not in edges or key in seen:
            return ""
        (parent, prefix) = edges[key]
        parent_tree = trees.get(parent[0])
        parent_own = _router_vars(parent_tree).get(parent[1], ("", ""))[1] if parent_tree else ""
        value = resolve(parent, seen + (key,)) + parent_own + prefix
        resolved[key] = value
        return value

    for key in edges:
        resolve(key)
    return resolved


# ---------- public API ----------

def extract_models(files: dict[str, str]) -> dict[str, list[Field]]:
    trees = _parse(files)
    classes: dict[str, ast.ClassDef] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.setdefault(node.name, node)

    def base_names(c: ast.ClassDef) -> list[str]:
        return [n for n in (unwrap_type(b) for b in c.bases) if n]

    model_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, c in classes.items():
            if name not in model_names and any(b == "BaseModel" or b in model_names for b in base_names(c)):
                model_names.add(name)
                changed = True

    cache: dict[str, list[Field]] = {}

    def fields_of(name: str, seen=()) -> list[Field]:
        if name in cache:
            return cache[name]
        c = classes[name]
        result: list[Field] = []
        for b in base_names(c):
            if b in model_names and b not in seen:
                for f in fields_of(b, seen + (name,)):
                    result = [x for x in result if x.name != f.name] + [f]
        for stmt in c.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fname = stmt.target.id
                if fname.startswith("model_config") or unwrap_type(stmt.annotation) == "ClassVar":
                    continue
                required = stmt.value is None or (isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis)
                if isinstance(stmt.value, ast.Call) and _call_name(stmt.value) == "Field":
                    first = stmt.value.args[0] if stmt.value.args else _kw(stmt.value, "default")
                    has_factory = _kw(stmt.value, "default_factory") is not None
                    required = not has_factory and (first is None or (isinstance(first, ast.Constant) and first.value is Ellipsis))
                f = Field(fname, unwrap_type(stmt.annotation) or "Any", required, display_type(stmt.annotation))
                existing = [i for i, x in enumerate(result) if x.name == fname]
                if existing:
                    result[existing[0]] = f
                else:
                    result.append(f)
        cache[name] = result
        return result

    return {n: fields_of(n) for n in sorted(model_names)}


def extract_routes(files: dict[str, str]) -> list[Route]:
    trees = _parse(files)
    model_names = set(extract_models(files))
    includes = _include_prefixes(trees)
    routes: list[Route] = []

    for path, tree in trees.items():
        local = _router_vars(tree)
        funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

        def full(var: str, sub: str) -> str:
            own = local.get(var, ("", ""))[1]
            p = includes.get((path, var), "") + own + sub
            return p if p.startswith("/") else "/" + p

        def body_model(fn) -> str | None:
            if fn is None:
                return None
            for a in fn.args.args + fn.args.kwonlyargs:
                t = unwrap_type(a.annotation)
                if t in model_names:
                    return t
            return None

        def response_node(call: ast.Call, fn):
            rm = _kw(call, "response_model")
            if rm is not None:
                return rm
            if fn is not None and fn.returns is not None and unwrap_type(fn.returns) not in PRIMITIVES:
                return fn.returns
            return None

        def response_model(call: ast.Call, fn) -> str | None:
            t = unwrap_type(response_node(call, fn))
            return None if t in (None, "None") else t

        def response_many(call: ast.Call, fn) -> bool:
            return is_many(response_node(call, fn))

        for fn in funcs.values():
            for dec in fn.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                var = dec.func.value.id if isinstance(dec.func.value, ast.Name) else None
                method = dec.func.attr
                if var not in local or (method not in HTTP_METHODS and method != "api_route"):
                    continue
                sub = _str(dec.args[0]) if dec.args else _str(_kw(dec, "path"))
                if sub is None:
                    continue
                if method == "api_route":
                    mnode = _kw(dec, "methods")
                    methods = [_str(e) for e in mnode.elts] if isinstance(mnode, (ast.List, ast.Tuple)) else ["GET"]
                else:
                    methods = [method]
                for m in filter(None, methods):
                    routes.append(Route(m.upper(), full(var, sub), path, fn.name, body_model(fn), response_model(dec, fn),
                                        response_many(dec, fn)))

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_api_route"):
                continue
            var = node.func.value.id if isinstance(node.func.value, ast.Name) else None
            if var not in local or not node.args:
                continue
            sub = _str(node.args[0])
            endpoint = node.args[1] if len(node.args) > 1 else _kw(node, "endpoint")
            fname = endpoint.id if isinstance(endpoint, ast.Name) else (ast.unparse(endpoint) if endpoint else "?")
            methods_node = _kw(node, "methods")
            methods = [_str(e) for e in methods_node.elts] if isinstance(methods_node, (ast.List, ast.Tuple)) else ["GET"]
            fn = funcs.get(fname)
            for m in filter(None, methods):
                routes.append(Route(m.upper(), full(var, sub or ""), path, fname, body_model(fn), response_model(node, fn),
                                    response_many(node, fn)))

    return sorted(routes, key=lambda r: (r.path, r.method))


def model_dependencies(files: dict[str, str]) -> dict[str, set[str]]:
    """model name -> models it depends on (base classes and field types), across the whole snapshot."""
    trees = _parse(files)
    models = extract_models(files)
    deps: dict[str, set[str]] = {name: {f.type for f in fields if f.type in models} for name, fields in models.items()}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in models:
                deps[node.name] |= {b for b in (unwrap_type(x) for x in node.bases) if b in models}
    return deps


def classes_defined(files: dict[str, str]) -> set[str]:
    return {n.name for t in _parse(files).values() for n in ast.walk(t) if isinstance(n, ast.ClassDef)}


def mounted_modules(files: dict[str, str], path: str) -> set[str]:
    """Router module files that `path` mounts with include_router (directly)."""
    trees = _parse(files)
    tree = trees.get(path)
    if tree is None:
        return set()
    aliases = _import_aliases(tree, path, trees)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id in aliases:
                out.add(aliases[arg.value.id][0])
            elif isinstance(arg, ast.Name) and arg.id in aliases:
                out.add(aliases[arg.id][0])
    return out
