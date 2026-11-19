"""Regression tests for the rev-3 (GitHub Pages) review findings."""
import httpx

from merge_docs.adapters.github_read import GitHubReader
from merge_docs.cli.pr_comment import BOT_LOGIN, is_fork, run
from merge_docs.core.contract import build_contracts
from merge_docs.core.render import MARKER
from merge_docs.core.site import build_site, page_name
from tests.test_actions import FakeGH


# ---------- Important 1: slugs can't inject HTML ----------

def test_page_name_is_filesystem_and_url_safe():
    assert page_name('demo/app/routers/x" onmouseover="alert(1)" a=') == "demo-app-routers-x-onmouseover-alert-1-a.html"


def test_index_links_cannot_break_out_of_href(tmp_path):
    files = {'app/routers/x" onmouseover="alert(1)" a=.py': "from fastapi import APIRouter\nrouter = APIRouter()\n"
                                                           "@router.get('/x')\ndef x(): ...\n"}
    build_site(build_contracts(files, "acme/shop"), {}, [], "acme/shop", tmp_path)
    index = (tmp_path / "index.html").read_text()
    assert 'onmouseover="' not in index
    assert '&quot;' in index  # the slug text itself is shown escaped


# ---------- Important 2: only the bot's own comment counts; 403 means fork only for forks ----------

def test_comment_from_another_user_with_the_marker_is_ignored():
    spoof = {"id": 5, "body": MARKER + "\nfake", "user": "mallory", "user_type": "User"}
    gh = FakeGH(comments=[spoof])
    assert run("acme/shop", 5, gh) == "created"
    assert not gh.updated


def test_bot_comment_is_updated():
    mine = {"id": 9, "body": MARKER + "\nold", "user": BOT_LOGIN, "user_type": "Bot"}
    gh = FakeGH(comments=[mine])
    assert run("acme/shop", 5, gh) == "updated" and gh.updated[0][0] == 9


def test_is_fork_compares_head_repo_with_this_repo():
    event = {"pull_request": {"head": {"repo": {"full_name": "someone/shop"}}}}
    assert is_fork(event, "acme/shop") is True
    assert is_fork({"pull_request": {"head": {"repo": {"full_name": "acme/shop"}}}}, "acme/shop") is False
    assert is_fork({"pull_request": {"head": {"repo": None}}}, "acme/shop") is True  # deleted fork


def test_reader_comments_include_author():
    gh = GitHubReader("t", transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json=[{"id": 1, "body": "x", "user": {"login": "github-actions[bot]", "type": "Bot"}}])))
    assert gh.issue_comments("acme/shop", 5) == [{"id": 1, "body": "x", "user": "github-actions[bot]", "user_type": "Bot"}]


# ---------- Important 4: recent merged PRs are the latest merges into the default branch ----------

def test_recent_merged_prs_filters_base_sorts_by_merge_time_and_pages():
    seen = []
    pages = {
        "1": [{"number": 9, "title": "old merge, recently commented", "html_url": "u9", "merged_at": "2026-01-01T00:00:00Z"}]
             + [{"number": 100 + i, "title": "closed", "html_url": "u", "merged_at": None} for i in range(99)],
        "2": [{"number": 12, "title": "newest", "html_url": "u12", "merged_at": "2026-11-18T00:00:00Z"},
              {"number": 11, "title": "newer", "html_url": "u11", "merged_at": "2026-11-17T00:00:00Z"}],
    }

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=pages.get(request.url.params["page"], []))

    gh = GitHubReader("t", transport=httpx.MockTransport(handler))
    prs = gh.recent_merged_prs("acme/shop", 2, base="main")
    assert [p["number"] for p in prs] == [12, 11]
    assert seen[0]["base"] == "main"
