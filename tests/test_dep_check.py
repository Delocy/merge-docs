"""PR comment: flag added or changed dependencies that have known advisories on OSV.dev."""
import json

import httpx

from merge_docs.adapters.github_read import _keep
from merge_docs.adapters.osv import query_advisories
from merge_docs.cli.pr_comment import run
from merge_docs.core.deps import DepFinding, Dependency, changed_dependencies, read_dependencies
from merge_docs.core.render import MARKER, render_comment
from tests.test_actions import BASE, FakeGH


def deps(text):
    return read_dependencies({"requirements.txt": text})


def test_changed_dependencies_finds_added_and_bumped_pins_only():
    old = deps("fastapi==0.115.0\npydantic==2.9.2\nuvicorn>=0.30\n")
    new = deps("fastapi==0.115.0\npydantic==2.10.0\nuvicorn>=0.31\njinja2==3.1.2\nrich\n")
    assert [(d.name, d.version, change) for d, change in changed_dependencies(old, new)] == [
        ("jinja2", "3.1.2", "added"), ("pydantic", "2.10.0", "changed from 2.9.2")]


def test_osv_adapter_sends_one_batch_and_maps_results():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        # results come back in query order: fastapi (clean), then jinja2
        return httpx.Response(200, json={"results": [{}, {"vulns": [{"id": "GHSA-a"}, {"id": "PYSEC-b"}]}]})

    found = query_advisories(deps("jinja2==3.1.2\nfastapi==0.115.0\n"), transport=httpx.MockTransport(handler))
    assert seen["url"] == "https://api.osv.dev/v1/querybatch"
    assert seen["body"]["queries"][0] == {"package": {"name": "fastapi", "ecosystem": "PyPI"}, "version": "0.115.0"}
    assert found == {"jinja2": ["GHSA-a", "PYSEC-b"], "fastapi": []}


def test_comment_with_only_dependency_findings():
    finding = DepFinding(Dependency("jinja2", "3.1.2", "jinja2==3.1.2", "requirements.txt"), "added",
                         tuple(f"GHSA-{i}" for i in range(5)))
    body = render_comment([], {}, False, dep_findings=[finding])
    assert body.startswith(MARKER)
    assert "`jinja2==3.1.2` (added): 5 known advisories" in body
    assert "https://osv.dev/vulnerability/GHSA-0" in body and "+2 more" in body


def test_comment_says_when_osv_was_unreachable():
    body = render_comment([], {}, True, osv_error=True)
    assert "OSV.dev could not be reached" in body


def test_snapshot_keeps_dependency_files():
    assert _keep("requirements.txt") and _keep("pyproject.toml") and not _keep("docs/readme.txt")


def test_pr_comment_flags_a_vulnerable_new_dependency():
    head = dict(BASE, **{"requirements.txt": "jinja2==3.1.2\n"})
    gh = FakeGH(head=head)
    assert run("acme/shop", 5, gh, advisories=lambda ds: {d.name: ["GHSA-x"] for d in ds}) == "created"
    assert "`jinja2==3.1.2` (added): 1 known advisory" in gh.created[0]


def test_pr_comment_skips_when_new_dependency_is_clean_and_api_unchanged():
    head = dict(BASE, **{"requirements.txt": "jinja2==3.1.6\n"})
    gh = FakeGH(head=head)
    assert run("acme/shop", 5, gh, advisories=lambda ds: {d.name: [] for d in ds}) == "skipped"


def test_pr_comment_still_posts_api_changes_when_osv_fails():
    def boom(ds):
        raise httpx.ConnectError("down")

    head = dict(BASE, **{"requirements.txt": "jinja2==3.1.2\n"})
    gh = FakeGH(head=head)
    gh.head["app/routers/health.py"] = BASE["app/routers/health.py"].replace('"/healthz"', '"/livez"')
    assert run("acme/shop", 5, gh, advisories=boom) == "created"
    assert "/healthz is now GET /livez" in gh.created[0] and "OSV.dev could not be reached" in gh.created[0]
