import csv
import io
import tarfile

import httpx

from merge_docs.adapters.github_read import ChangedFile, GitHubReader
from merge_docs.cli.validate import run_validation
from tests.sample import sample_files

BASE = sample_files()
HEAD = dict(BASE)
HEAD["app/models/order.py"] = BASE["app/models/order.py"].replace("    status: str\n", "    status: str\n    eta: str | None = None\n")
HEAD["docs/features/app/routers/orders.md"] = "Use `DELETE /v1/orders/{id}` to cancel.\n"
HEAD["app/routers/orders.py"] = BASE["app/routers/orders.py"].replace('@router.delete("/{order_id}")', '@router.post("/{order_id}/cancel")')


class FakeGitHub:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on

    def base_and_head(self, repo, pr):
        if pr == self.fail_on:
            raise httpx.HTTPStatusError("404", request=httpx.Request("GET", "https://x"), response=httpx.Response(404))
        return ("base1", "head1") if pr == 42 else ("base2", "base2")

    def pr_files(self, repo, pr):
        return [ChangedFile("app/models/order.py", "modified", "+eta")]

    def snapshot(self, repo, sha):
        return dict(HEAD if sha == "head1" else BASE)


def rows_of(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def test_api_changes_give_comment_pages_and_summary(tmp_path):
    run_validation("acme/shop", [42], gh=FakeGitHub(), out_dir=tmp_path)
    comment = (tmp_path / "42-comment.md").read_text()
    assert "response field `eta` added (str | None, optional)" in comment
    assert "DELETE /v1/orders/{order_id} is now POST /v1/orders/{order_id}/cancel" in comment
    assert "Notes to update" in comment and "`DELETE /v1/orders/{id}` no longer exists" in comment
    page = (tmp_path / "42-app-routers-orders.md").read_text()
    assert "| `eta` | str \\| None | no |" in page  # the pipe is escaped so the table keeps its columns
    (row,) = rows_of(tmp_path / "summary.csv")
    assert row["modules_changed"] == "1" and int(row["changes"]) >= 2 and row["stale_mentions"] == "1"
    assert row["endpoints"] == "7" and row["error"] == ""
    assert 0 < float(row["declared_response_share"]) < 1


def test_pr_without_api_changes(tmp_path):
    run_validation("acme/shop", [7], gh=FakeGitHub(), out_dir=tmp_path)
    (row,) = rows_of(tmp_path / "summary.csv")
    assert row["changes"] == "0" and row["modules_changed"] == "0"
    assert "No API changes" in (tmp_path / "7-comment.md").read_text()
    assert not list(tmp_path.glob("7-app-*.md"))


def test_github_error_is_recorded_and_other_prs_still_run(tmp_path):
    run_validation("acme/shop", [5, 42], gh=FakeGitHub(fail_on=5), out_dir=tmp_path)
    rows = rows_of(tmp_path / "summary.csv")
    assert rows[0]["pr"] == "5" and "404" in rows[0]["error"]
    assert rows[1]["pr"] == "42" and rows[1]["error"] == ""


def _tarball(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"acme-shop-abc123/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_reader_snapshot_keeps_python_and_feature_notes():
    blob = _tarball({"app/a.py": "x = 1", "docs/features/app/a.md": "doc", "README.md": "no"})

    def handler(request):
        assert request.headers["authorization"] == "Bearer t0ken"
        return httpx.Response(200, content=blob)

    gh = GitHubReader("t0ken", transport=httpx.MockTransport(handler))
    assert gh.snapshot("acme/shop", "abc123") == {"app/a.py": "x = 1", "docs/features/app/a.md": "doc"}


def test_reader_base_is_the_merge_base_not_the_moving_branch_tip():
    def handler(request):
        if request.url.path == "/repos/acme/shop/pulls/9":
            return httpx.Response(200, json={"base": {"sha": "tip"}, "head": {"sha": "h"}})
        assert request.url.path == "/repos/acme/shop/compare/tip...h"
        return httpx.Response(200, json={"merge_base_commit": {"sha": "mb"}})

    gh = GitHubReader("t", transport=httpx.MockTransport(handler))
    assert gh.base_and_head("acme/shop", 9) == ("mb", "h")


def test_reader_pr_files_paginates():
    pages = {"1": [{"filename": f"f{i}.py", "status": "modified", "patch": "+x"} for i in range(100)],
             "2": [{"filename": "last.py", "status": "added"}]}
    gh = GitHubReader("t", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=pages.get(r.url.params.get("page", "1"), []))))
    files = gh.pr_files("acme/shop", 7)
    assert len(files) == 101 and files[-1] == ChangedFile("last.py", "added", "")
