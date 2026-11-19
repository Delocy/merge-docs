"""Post or update the "API changes" comment on a pull request. Run by GitHub Actions on pull_request.

In Actions:  python -m merge_docs.cli.pr_comment   (reads GITHUB_REPOSITORY, GITHUB_EVENT_PATH, GITHUB_TOKEN)
By hand:     GITHUB_TOKEN=... python -m merge_docs.cli.pr_comment --repo owner/name --pr 12
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Literal

import httpx

from merge_docs.adapters.osv import query_advisories
from merge_docs.core.contract import build_contracts
from merge_docs.core.deps import DepFinding, changed_dependencies, read_dependencies
from merge_docs.core.diff import diff_contracts
from merge_docs.core.notes import notes_path, stale_mentions
from merge_docs.core.render import MARKER, render_comment

Outcome = Literal["created", "updated", "skipped", "unchanged"]
BOT_LOGIN = "github-actions[bot]"  # the identity behind the workflow's GITHUB_TOKEN


def is_fork(event: dict, repo: str) -> bool:
    head_repo = (event.get("pull_request", {}).get("head", {}) or {}).get("repo")
    return not head_repo or head_repo.get("full_name") != repo


def _code(files: dict[str, str]) -> dict[str, str]:
    return {p: t for p, t in files.items() if p.endswith(".py")}


def check_dependencies(base_files: dict[str, str], head_files: dict[str, str], advisories) -> tuple[list[DepFinding], bool]:
    changed = changed_dependencies(read_dependencies(base_files), read_dependencies(head_files))
    if not changed:
        return [], False
    try:
        found = advisories([d for d, _ in changed])
    except (httpx.HTTPError, KeyError, ValueError):
        return [], True
    return [DepFinding(d, change, tuple(found.get(d.name, []))) for d, change in changed if found.get(d.name)], False


def build_comment(repo: str, pr: int, gh: Any, had_changes_before: bool, advisories=query_advisories) -> str | None:
    base, head = gh.base_and_head(repo, pr)
    base_files = gh.snapshot(repo, base)
    head_files = base_files if head == base else gh.snapshot(repo, head)
    old = build_contracts(_code(base_files), repo)
    new = build_contracts(_code(head_files), repo)
    changes = diff_contracts(old, new)
    stale = {m: stale_mentions(head_files[notes_path(m)], new, old) for m in new if notes_path(m) in head_files}
    findings, osv_error = check_dependencies(base_files, head_files, advisories)
    return render_comment(changes, stale, had_changes_before, dep_findings=findings, osv_error=osv_error)


def run(repo: str, pr: int, gh: Any, advisories=query_advisories) -> Outcome:
    # Only our own comment counts: anyone can post a comment that starts with the marker.
    existing = next((c for c in gh.issue_comments(repo, pr)
                     if c["body"].startswith(MARKER) and c.get("user") == BOT_LOGIN), None)
    body = build_comment(repo, pr, gh, had_changes_before=existing is not None, advisories=advisories)
    if body is None:
        return "skipped"
    if existing is None:
        gh.create_comment(repo, pr, body)
        return "created"
    if existing["body"].strip() == body.strip():
        return "unchanged"
    gh.update_comment(repo, existing["id"], body)
    return "updated"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int)
    args = parser.parse_args(argv)
    pr, event = args.pr, {}
    if os.environ.get("GITHUB_EVENT_PATH"):
        with open(os.environ["GITHUB_EVENT_PATH"]) as f:
            event = json.load(f)
        pr = pr or event["pull_request"]["number"]
    token = os.environ.get("GITHUB_TOKEN")
    if not (args.repo and pr and token):
        parser.error("needs --repo, --pr (or GITHUB_EVENT_PATH) and GITHUB_TOKEN")

    from merge_docs.adapters.github_read import GitHubReader

    gh = GitHubReader(token)
    try:
        outcome = run(args.repo, pr, gh)
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 403 and event and is_fork(event, args.repo):
            # PRs from forks get a read-only token: show the comment in the log instead of failing the check.
            print("No permission to comment on a fork PR. The comment would have been:\n")
            print(build_comment(args.repo, pr, gh, had_changes_before=False) or "(no API changes)")
            return
        raise
    print(f"PR #{pr}: comment {outcome}")


if __name__ == "__main__":
    main()
