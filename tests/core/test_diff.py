from merge_docs.core.contract import EndpointContract, FieldSpec, ModuleContract, Shape
from merge_docs.core.diff import Change, diff_contracts

M = "app/routers/orders.py"
NONE = Shape(False, None, ())


def shape(*fields, model="Order"):
    return Shape(True, model, tuple(FieldSpec(*f) for f in fields))


def ep(method, path, func, request=NONE, response=NONE):
    return EndpointContract(method, path, func, request, response)


def mod(*endpoints, module=M):
    return {module: ModuleContract(module, "shop/" + module, tuple(endpoints))}


BASE = ep("GET", "/v1/orders/{order_id}", "get_order", response=shape(("id", "int", True), ("status", "str", True)))


def kinds(changes):
    return [c.kind for c in changes]


def test_identical_contracts_have_no_changes():
    assert diff_contracts(mod(BASE), mod(BASE)) == []


def test_endpoint_added():
    new = ep("POST", "/v1/orders", "create_order")
    changes = diff_contracts(mod(BASE), mod(BASE, new))
    assert changes == [Change(M, "endpoint_added", "POST /v1/orders", "POST /v1/orders added")]


def test_endpoint_removed():
    assert kinds(diff_contracts(mod(BASE), mod())) == ["endpoint_removed"]


def test_rename_with_same_handler_is_one_change():
    renamed = ep("GET", "/v1/orders/{order_id}/detail", "get_order", response=BASE.response)
    changes = diff_contracts(mod(BASE), mod(renamed))
    assert kinds(changes) == ["endpoint_renamed"]
    assert changes[0].endpoint == "GET /v1/orders/{order_id}/detail"
    assert "GET /v1/orders/{order_id}" in changes[0].detail


def test_path_param_rename_alone_is_not_a_change():
    same = ep("GET", "/v1/orders/{id}", "get_order", response=BASE.response)
    assert diff_contracts(mod(BASE), mod(same)) == []


def test_field_added_removed_retyped_and_required_changed():
    after = ep("GET", "/v1/orders/{order_id}", "get_order",
               response=shape(("id", "str", True), ("eta", "str", False)))
    changes = diff_contracts(mod(BASE), mod(after))
    assert sorted(kinds(changes)) == ["field_added", "field_removed", "field_retyped"]
    retyped = next(c for c in changes if c.kind == "field_retyped")
    assert "response" in retyped.detail and "int" in retyped.detail and "str" in retyped.detail

    optional = ep("GET", "/v1/orders/{order_id}", "get_order",
                  response=shape(("id", "int", True), ("status", "str", False)))
    assert kinds(diff_contracts(mod(BASE), mod(optional))) == ["field_required_changed"]


def test_shape_declared_and_undeclared():
    undeclared = ep("GET", "/v1/orders/{order_id}", "get_order")
    assert kinds(diff_contracts(mod(BASE), mod(undeclared))) == ["shape_undeclared"]
    assert kinds(diff_contracts(mod(undeclared), mod(BASE))) == ["shape_declared"]


def test_new_module_adds_each_endpoint_and_removed_module_removes_them():
    other = mod(ep("GET", "/healthz", "healthz"), ep("GET", "/readyz", "readyz"), module="app/routers/health.py")
    assert kinds(diff_contracts(mod(BASE), {**mod(BASE), **other})) == ["endpoint_added", "endpoint_added"]
    assert kinds(diff_contracts({**mod(BASE), **other}, mod(BASE))) == ["endpoint_removed", "endpoint_removed"]


def test_changes_are_sorted_by_module_then_endpoint():
    a = mod(ep("GET", "/b", "b"), module="z.py")
    b = mod(ep("GET", "/a", "a"), module="a.py")
    changes = diff_contracts({}, {**a, **b})
    assert [c.module for c in changes] == ["a.py", "z.py"]
