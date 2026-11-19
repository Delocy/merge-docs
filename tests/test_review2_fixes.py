"""Regression tests for the rev-2 final-review findings."""
from merge_docs.cli.validate import run_validation
from merge_docs.core.contract import build_contracts
from merge_docs.core.diff import diff_contracts
from merge_docs.core.notes import stale_mentions
from merge_docs.core.render import render_comment
from tests.sample import sample_files

ROUTER = (
    "from fastapi import APIRouter\nfrom typing import Optional, List\nfrom pydantic import BaseModel\n"
    "router = APIRouter()\n"
    "class O(BaseModel):\n    x: {field}\n"
    "@router.get('/o', response_model={resp})\n"
    "def get_o(): ...\n"
)


def contracts(field="int", resp="O"):
    return build_contracts({"app/o.py": ROUTER.replace("{field}", field).replace("{resp}", resp)}, "acme/shop")


# ---------- Important 1: stale endpoint mentions must be caused by the PR ----------

def test_mention_of_another_modules_endpoint_is_not_stale():
    files = sample_files()
    both = build_contracts(files, "acme/shop")
    note = "Call `GET /healthz` first, then `GET /v1/orders/{id}`."
    assert stale_mentions(note, both, both) == []


def test_already_stale_mention_is_not_reported_on_unrelated_prs():
    both = build_contracts(sample_files(), "acme/shop")
    assert stale_mentions("See `GET /v0/ancient`.", both, both) == []


def test_mention_made_stale_by_this_pr_is_reported():
    old = build_contracts(sample_files(), "acme/shop")
    files = sample_files()
    files["app/routers/health.py"] = files["app/routers/health.py"].replace('"/healthz"', '"/livez"')
    new = build_contracts(files, "acme/shop")
    assert stale_mentions("Call `GET /healthz` first.", new, old) == ["`GET /healthz` no longer exists"]


def test_no_comment_on_a_pr_without_api_changes_even_with_notes(tmp_path):
    class GH:
        def base_and_head(self, repo, pr):
            return "s", "s"

        def snapshot(self, repo, sha):
            return sample_files() | {"docs/features/app/routers/orders.md": "Call `GET /healthz` and `GET /v0/gone`."}

    (row,) = run_validation("acme/shop", [3], gh=GH(), out_dir=tmp_path)
    assert row["stale_mentions"] == 0
    assert render_comment([], {"app/routers/orders.py": []}, had_changes_before=False) is None


# ---------- Important 2: list-ness and nullability are part of the contract ----------

def test_response_becoming_a_list_is_reported():
    changes = diff_contracts(contracts(resp="O"), contracts(resp="list[O]"))
    assert [c.kind for c in changes] == ["field_retyped"]
    assert "list[O]" in changes[0].detail


def test_field_becoming_a_list_is_reported():
    changes = diff_contracts(contracts(field="int"), contracts(field="list[int]"))
    assert [c.kind for c in changes] == ["field_retyped"] and "list[int]" in changes[0].detail


def test_field_becoming_nullable_is_reported_and_typing_spellings_are_equal():
    changes = diff_contracts(contracts(field="int"), contracts(field="int | None"))
    assert [c.kind for c in changes] == ["field_retyped"] and "int | None" in changes[0].detail
    assert diff_contracts(contracts(field="Optional[int]"), contracts(field="int | None")) == []
    assert diff_contracts(contracts(field="List[int]"), contracts(field="list[int]")) == []


# ---------- re-graded minor: reruns must not duplicate summary rows ----------

def test_rerun_replaces_summary_rows(tmp_path):
    class GH:
        def base_and_head(self, repo, pr):
            return "s", "s"

        def snapshot(self, repo, sha):
            return sample_files()

    run_validation("acme/shop", [1], gh=GH(), out_dir=tmp_path)
    run_validation("acme/shop", [1], gh=GH(), out_dir=tmp_path)
    assert (tmp_path / "summary.csv").read_text().count("\n") == 2  # header + one row
