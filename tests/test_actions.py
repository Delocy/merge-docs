"""The two commands GitHub Actions runs: pr_comment (on pull_request) and build_site (on push)."""
import json

import httpx

from merge_docs.adapters.github_read import GitHubReader
from merge_docs.cli import build_site as build_site_cli
from merge_docs.cli.pr_comment import BOT_LOGIN, run
from merge_docs.core.render import MARKER
from tests.sample import sample_files

BASE = sample_files()
HEAD = dict(BASE)
HEAD["app/routers/health.py"] = BASE["app/routers/health.py"].replace('"/healthz"', '"/livez"')


class FakeGH:
    def __init__(self, comments=None, head=HEAD):
        self.comments = comments or []
        self.head = head
        self.created, self.updated = [], []

    def base_and_head(self, repo, pr):
        return "base", "head"

    def snapshot(self, repo, sha):
        return dict(self.head if sha == "head" else BASE)

    def issue_comments(self, repo, pr):
        return self.comments

    def create_comment(self, repo, pr, body):
        self.created.append(body)
        return 101

    def update_comment(self, repo, comment_id, body):
        self.updated.append((comment_id, body))


def test_creates_comment_when_api_changed_and_none_exists():
    gh = FakeGH()
    assert run("acme/shop", 5, gh) == "created"
    assert gh.created[0].startswith(MARKER) and "/healthz is now GET /livez" in gh.created[0]


def test_updates_existing_comment_found_by_marker():
    gh = FakeGH(comments=[{"id": 7, "body": "LGTM", "user": "ana"}, {"id": 9, "body": MARKER + "\nold", "user": BOT_LOGIN}])
    assert run("acme/shop", 5, gh) == "updated"
    assert gh.updated[0][0] == 9 and not gh.created


def test_skips_when_no_api_changes_and_no_comment():
    gh = FakeGH(head=BASE)
    assert run("acme/shop", 5, gh) == "skipped"
    assert not gh.created and not gh.updated


def test_reverted_pr_updates_comment_to_no_changes():
    gh = FakeGH(comments=[{"id": 9, "body": MARKER + "\nold", "user": BOT_LOGIN}], head=BASE)
    assert run("acme/shop", 5, gh) == "updated"
    assert "No API changes" in gh.updated[0][1]


def test_same_body_is_not_rewritten():
    gh = FakeGH()
    run("acme/shop", 5, gh)
    gh2 = FakeGH(comments=[{"id": 9, "body": gh.created[0], "user": BOT_LOGIN}])
    assert run("acme/shop", 5, gh2) == "unchanged"
    assert not gh2.updated


def test_reader_comment_calls():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, request.content and json.loads(request.content)))
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": 1, "body": "x", "user": {"login": "ana", "type": "User"}}])
        return httpx.Response(201 if request.method == "POST" else 200, json={"id": 55})

    gh = GitHubReader("t", transport=httpx.MockTransport(handler))
    assert gh.issue_comments("acme/shop", 5) == [{"id": 1, "body": "x", "user": "ana", "user_type": "User"}]
    assert gh.create_comment("acme/shop", 5, "hi") == 55
    gh.update_comment("acme/shop", 55, "bye")
    assert seen[1] == ("POST", "/repos/acme/shop/issues/5/comments", {"body": "hi"})
    assert seen[2] == ("PATCH", "/repos/acme/shop/issues/comments/55", {"body": "bye"})


def test_reader_recent_merged_prs_skips_unmerged():
    def handler(request):
        assert request.url.params["state"] == "closed"
        if request.url.params["page"] != "1":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"number": 3, "title": "a", "html_url": "u", "merged_at": "2026-11-18T01:00:00Z"},
                                         {"number": 2, "title": "b", "html_url": "u", "merged_at": None}])

    gh = GitHubReader("t", transport=httpx.MockTransport(handler))
    assert [p["number"] for p in gh.recent_merged_prs("acme/shop", 10)] == [3]


def test_build_site_reads_checkout_and_merged_changes(tmp_path):
    repo_dir = tmp_path / "repo"
    for path, text in HEAD.items():
        (repo_dir / path).parent.mkdir(parents=True, exist_ok=True)
        (repo_dir / path).write_text(text)
    (repo_dir / "docs/features/app/routers").mkdir(parents=True)
    (repo_dir / "docs/features/app/routers/health.md").write_text("Probe `GET /livez`.")
    (repo_dir / ".venv/lib").mkdir(parents=True)
    (repo_dir / ".venv/lib/x.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")

    files = build_site_cli.read_checkout(repo_dir)
    assert "app/routers/health.py" in files and "docs/features/app/routers/health.md" in files
    assert not any(p.startswith(".venv") for p in files)

    class GH(FakeGH):
        def recent_merged_prs(self, repo, limit, base=None):
            return [{"number": 4, "title": "Rename probe", "html_url": "https://x/4", "merged_at": "2026-11-18T00:00:00Z"}]

    merged = build_site_cli.merged_changes("acme/shop", GH(), 10)
    assert merged[0].pr == 4 and merged[0].merged_at == "2026-11-18"
