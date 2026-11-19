from pathlib import Path

import pytest

from merge_docs.core.contract import FieldSpec, Shape, build_contracts
from merge_docs.core.extract import router_modules

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_api"


@pytest.fixture(scope="module")
def files():
    return {str(p.relative_to(FIXTURE)): p.read_text() for p in FIXTURE.rglob("*.py")}


@pytest.fixture(scope="module")
def contracts(files):
    return build_contracts(files, "acme/shop")


def endpoint(contracts, module, key):
    return next(e for e in contracts[module].endpoints if f"{e.method} {e.path}" == key)


def test_request_shape_is_declared_and_nested_one_level(contracts):
    e = endpoint(contracts, "app/routers/orders.py", "POST /v1/orders")
    assert e.request.declared and e.request.model == "OrderCreate"
    names = [f.name for f in e.request.fields]
    assert "items" in names and "items.sku" in names
    assert FieldSpec("note", "str | None", False) in e.request.fields  # the full type, not just "str"


def test_undeclared_response_is_marked(contracts):
    e = endpoint(contracts, "app/routers/orders.py", "DELETE /v1/orders/{order_id}")
    assert e.response == Shape(False, None, ())


def test_endpoint_without_body_has_undeclared_request(contracts):
    e = endpoint(contracts, "app/routers/orders.py", "GET /v1/orders/{order_id}")
    assert e.request == Shape(False, None, ())
    assert e.response.model == "Order"


def test_slug_uses_repo_name_and_module_path(contracts):
    assert contracts["app/routers/orders.py"].slug == "shop/app/routers/orders"


def test_every_router_module_appears(files, contracts):
    assert set(contracts) == set(router_modules(files))


def test_a_file_with_a_syntax_error_is_skipped_not_fatal(files):
    broken = dict(files, **{"app/routers/half_written.py": "from fastapi import APIRouter\nrouter = APIRouter(\n"})
    assert "app/routers/orders.py" in build_contracts(broken, "acme/shop")
