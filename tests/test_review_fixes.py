"""Regression tests for the rev-1 final-review findings that still apply (Important 2-4)."""
from merge_docs.core.extract import extract_models, extract_routes, router_modules


# ---------- Important 2: common FastAPI layouts ----------

LAYOUT = {
    "app/__init__.py": "",
    "app/main.py": (
        "from fastapi import FastAPI\n"
        "from .routers import orders, items\n"
        "def create_app():\n"
        "    app = FastAPI()\n"
        "    app.include_router(orders.router, prefix='/v1')\n"
        "    app.include_router(items.router, prefix='/v1')\n"
        "    return app\n"
    ),
    "app/routers/__init__.py": "",
    "app/routers/orders.py": (
        "from fastapi import APIRouter\n"
        "router: APIRouter = APIRouter(prefix='/orders')\n"
        "@router.get('/{order_id}')\n"
        "def get_order(order_id: int): ...\n"
    ),
    "app/routers/items.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/items')\n"
        "@router.api_route('/{item_id}', methods=['GET', 'PUT'])\n"
        "def item(item_id: int): ...\n"
    ),
}


def keys(files):
    return {(r.method, r.path) for r in extract_routes(files)}


def test_relative_import_and_app_factory_keep_include_prefix():
    assert ("GET", "/v1/orders/{order_id}") in keys(LAYOUT)


def test_annotated_router_assignment_is_found():
    assert "app/routers/orders.py" in router_modules(LAYOUT)


def test_api_route_with_methods_is_extracted():
    assert {("GET", "/v1/items/{item_id}"), ("PUT", "/v1/items/{item_id}")} <= keys(LAYOUT)


# ---------- Important 3: changes that affect a router without editing it ----------

def test_base_class_change_in_another_file_touches_router():
    from merge_docs.core.impact import touched_modules
    from tests.sample import sample_files
    files = sample_files()
    files["app/models/base.py"] = "from pydantic import BaseModel\nclass Base(BaseModel):\n    id: int\n"
    files["app/models/order.py"] = files["app/models/order.py"].replace(
        "class Base(BaseModel):\n    id: int\n", "from app.models.base import Base\n")
    assert touched_modules(["app/models/base.py"], files) == ["app/routers/orders.py"]


def test_nested_model_change_touches_router():
    from merge_docs.core.impact import touched_modules
    from tests.sample import sample_files
    files = sample_files()
    files["app/models/item.py"] = "from pydantic import BaseModel\nclass Item(BaseModel):\n    sku: str\n"
    files["app/models/order.py"] = files["app/models/order.py"].replace(
        "class Item(BaseModel):\n    sku: str\n    quantity: int = 1\n", "from app.models.item import Item\n")
    assert touched_modules(["app/models/item.py"], files) == ["app/routers/orders.py"]


def test_include_router_change_touches_mounted_routers():
    from merge_docs.core.impact import touched_modules
    from tests.sample import sample_files
    assert touched_modules(["app/main.py"], sample_files()) == ["app/routers/health.py", "app/routers/orders.py"]


# ---------- Important 4: test files never shadow app models or get drafted ----------

def test_test_files_do_not_shadow_models_or_count_as_routers():
    from tests.sample import sample_files
    files = sample_files()
    files["tests/test_orders.py"] = (
        "from pydantic import BaseModel\nfrom fastapi import APIRouter\n"
        "class Order(BaseModel):\n    foo: int\n"
        "router = APIRouter()\n"
    )
    assert [f.name for f in extract_models(files)["Order"]][:2] == ["id", "customer_id"]
    assert "tests/test_orders.py" not in router_modules(files)


def test_model_only_change_touches_the_routers_that_use_it():
    from merge_docs.core.impact import touched_modules
    from tests.sample import sample_files
    assert touched_modules(["app/models/order.py"], sample_files()) == ["app/routers/orders.py"]
    assert touched_modules(["README.md"], sample_files()) == []
