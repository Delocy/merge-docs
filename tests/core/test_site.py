import json

import pytest

from merge_docs.core.contract import build_contracts
from merge_docs.core.diff import Change
from merge_docs.core.site import MergedChanges, build_site
from tests.sample import sample_files


@pytest.fixture
def site(tmp_path):
    contracts = build_contracts(sample_files(), "acme/shop")
    notes = {"app/routers/orders.py": "Orders move `new` → `paid`.\n\n<script>alert('x')</script> Call `GET /v1/orders/{id}`."}
    changes = [MergedChanges(12, "Add order cancel", "https://github.com/acme/shop/pull/12", "2026-11-18",
                             (Change("app/routers/orders.py", "endpoint_added", "POST /v1/orders/{order_id}/cancel",
                                     "POST /v1/orders/{order_id}/cancel added"),))]
    build_site(contracts, notes, changes, "acme/shop", tmp_path)
    return tmp_path


def test_all_files_exist(site):
    for name in ["index.html", "changes.html", "search.json", "style.css", "search.js",
                 "features/shop-app-routers-orders.html", "features/shop-app-routers-health.html"]:
        assert (site / name).exists(), name


def test_search_index_lists_slugs_paths_and_fields(site):
    index = json.loads((site / "search.json").read_text())
    orders = next(e for e in index if e["slug"] == "shop/app/routers/orders")
    assert orders["url"] == "features/shop-app-routers-orders.html"
    assert "POST /v1/orders" in orders["endpoints"]
    assert "customer_id" in orders["fields"] and "items.sku" in orders["fields"]


def test_feature_page_has_tables_and_not_declared(site):
    page = (site / "features/shop-app-routers-orders.html").read_text()
    assert '<span class="method m-post">POST</span> <span>/v1/orders</span>' in page
    assert "<td><code>customer_id</code></td>" in page
    assert "No request body declared" in page or "Not declared" in page


def test_notes_are_escaped_but_inline_code_kept(site):
    page = (site / "features/shop-app-routers-orders.html").read_text()
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert "<code>GET /v1/orders/{id}</code>" in page


def test_changes_page_lists_merged_prs(site):
    page = (site / "changes.html").read_text()
    assert "Add order cancel" in page and "https://github.com/acme/shop/pull/12" in page
    assert "POST /v1/orders/{order_id}/cancel added" in page


def test_changes_page_empty_state(tmp_path):
    build_site(build_contracts(sample_files(), "acme/shop"), {}, [], "acme/shop", tmp_path)
    assert "No merged PRs with API changes yet" in (tmp_path / "changes.html").read_text()


def test_feature_without_notes_says_where_to_add_them(tmp_path):
    build_site(build_contracts(sample_files(), "acme/shop"), {}, [], "acme/shop", tmp_path)
    page = (tmp_path / "features/shop-app-routers-health.html").read_text()
    assert "docs/features/app/routers/health.md" in page
