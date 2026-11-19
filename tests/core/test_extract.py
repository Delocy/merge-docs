from pathlib import Path

import pytest

from merge_docs.core.extract import Route, extract_models, extract_routes, router_modules

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_api"


@pytest.fixture(scope="module")
def files() -> dict[str, str]:
    return {str(p.relative_to(FIXTURE)): p.read_text() for p in FIXTURE.rglob("*.py")}


def _by_key(routes):
    return {(r.method, r.path): r for r in routes}


def test_routes_join_include_and_router_prefixes(files):
    routes = _by_key(extract_routes(files))
    r = routes[("GET", "/v1/orders/{order_id}")]
    assert r == Route("GET", "/v1/orders/{order_id}", "app/routers/orders.py", "get_order", None, "Order")
    assert ("POST", "/v1/orders") in routes
    assert ("GET", "/v1/orders") in routes
    assert ("GET", "/healthz") in routes


def test_body_model_comes_from_typed_parameter(files):
    routes = _by_key(extract_routes(files))
    assert routes[("POST", "/v1/orders")].body_model == "OrderCreate"
    assert routes[("GET", "/v1/orders/{order_id}")].body_model is None


def test_add_api_route_is_detected(files):
    routes = _by_key(extract_routes(files))
    r = routes[("POST", "/v1/orders/export")]
    assert r.func == "_legacy_export"
    assert r.response_model == "OrderList"


def test_response_model_none_when_undeclared(files):
    routes = _by_key(extract_routes(files))
    assert routes[("DELETE", "/v1/orders/{order_id}")].response_model is None
    assert routes[("GET", "/healthz")].response_model is None


def test_response_model_falls_back_to_return_annotation():
    src = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/a')\n"
        "def a() -> Thing:\n    ...\n"
    )
    (r,) = extract_routes({"m.py": src})
    assert r.response_model == "Thing"


def test_models_flatten_inheritance(files):
    models = extract_models(files)
    names = [f.name for f in models["Order"]]
    assert names == ["id", "customer_id", "items", "status"]


def test_generic_and_optional_unwrapped(files):
    models = extract_models(files)
    by_name = {f.name: f for f in models["OrderCreate"]}
    assert by_name["items"].type == "Item"
    assert by_name["note"].type == "str"
    assert by_name["note"].required is False
    assert by_name["customer_id"].required is True
    assert {f.name: f.type for f in models["OrderList"]}["orders"] == "Order"


def test_never_imports_code(files):
    # broken_on_import.py raises at import time; static parsing must still read it.
    routes = _by_key(extract_routes(files))
    assert ("GET", "/boom/x") in routes


def test_router_modules(files):
    assert set(router_modules(files)) == {
        "app/routers/orders.py",
        "app/routers/health.py",
        "app/broken_on_import.py",
    }
