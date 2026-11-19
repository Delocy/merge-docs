from merge_docs.core.contract import EndpointContract, FieldSpec, ModuleContract, Shape
from merge_docs.core.diff import Change
from merge_docs.core.notes import mentions, notes_path, stale_mentions
from merge_docs.core.render import MARKER, render_comment, render_module_markdown

NONE = Shape(False, None, ())
ORDER = Shape(True, "Order", (FieldSpec("id", "int", True), FieldSpec("status", "str", True)))


def contract(*endpoints):
    return ModuleContract("app/routers/orders.py", "shop/app/routers/orders", tuple(endpoints))


GET = EndpointContract("GET", "/v1/orders/{order_id}", "get_order", NONE, ORDER)
DELETE = EndpointContract("DELETE", "/v1/orders/{order_id}", "cancel_order", NONE, NONE)

NOTE = """# Orders

Call `GET /v1/orders/{id}` to read one order. The `status` field moves new → paid.
Install with `pip install shop`, and see `json` output.

```bash
curl `POST /v1/legacy`
```
"""


def test_notes_path():
    assert notes_path("app/routers/orders.py") == "docs/features/app/routers/orders.md"


def test_mentions_ignore_code_fences_and_non_identifiers():
    endpoints, fields = mentions(NOTE)
    assert endpoints == {"GET /v1/orders/{id}"}
    assert "status" in fields and "json" in fields
    assert not any(" " in f for f in fields)  # `pip install shop` is not a field mention


def repo(*endpoints):
    return {"app/routers/orders.py": contract(*endpoints)}


def test_stale_endpoint_is_reported_with_param_names_ignored():
    assert stale_mentions(NOTE, repo(GET), repo(GET)) == []
    # GET is gone (only DELETE remains), and with it the `status` response field the note mentions.
    assert stale_mentions(NOTE, repo(DELETE), repo(GET)) == ["`GET /v1/orders/{id}` no longer exists",
                                                            "`status` no longer exists"]


def test_stale_field_needs_the_old_contract_to_avoid_noise():
    without_status = EndpointContract("GET", "/v1/orders/{order_id}", "get_order", NONE,
                                      Shape(True, "Order", (FieldSpec("id", "int", True),)))
    # Without the old snapshot, nothing is judged (`json` would be noise).
    assert stale_mentions(NOTE, repo(without_status), None) == []
    # With it, a field that existed before and is gone now is stale; `json` never existed, so it is ignored.
    assert stale_mentions(NOTE, repo(without_status), repo(GET)) == ["`status` no longer exists"]


CHANGES = [
    Change("app/routers/orders.py", "field_added", "POST /v1/orders", "request field `note` added (str, optional)"),
    Change("app/routers/orders.py", "endpoint_removed", "DELETE /v1/orders/{order_id}", "DELETE /v1/orders/{order_id} removed"),
    Change("app/routers/health.py", "endpoint_added", "GET /readyz", "GET /readyz added"),
]


def test_no_comment_when_nothing_changed_and_nothing_before():
    assert render_comment([], {}, had_changes_before=False) is None


def test_reverted_pr_says_no_api_changes():
    body = render_comment([], {}, had_changes_before=True)
    assert body.startswith(MARKER) and "No API changes" in body


def test_comment_groups_by_module_and_lists_stale_notes():
    body = render_comment(CHANGES, {"app/routers/orders.py": ["`GET /v1/orders/{id}` no longer exists"]},
                          had_changes_before=False)
    assert body.startswith(MARKER)
    assert body.index("app/routers/health.py") < body.index("app/routers/orders.py")
    assert "request field `note` added (str, optional)" in body
    assert "Notes to update" in body and "docs/features/app/routers/orders.md" in body


def test_module_markdown_shows_tables_and_not_declared():
    md = render_module_markdown(contract(GET, DELETE), notes=None)
    assert "## GET /v1/orders/{order_id}" in md
    assert "| `status` | str | yes |" in md
    assert "Not declared in the code" in md
    assert "docs/features/app/routers/orders.md" in md  # tells people where to add notes


def test_module_markdown_includes_notes():
    assert "moves new → paid" in render_module_markdown(contract(GET), notes=NOTE)
