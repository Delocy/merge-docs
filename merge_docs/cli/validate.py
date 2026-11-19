"""Run the contract diff on past PRs to decide whether the catalogue is worth building. Free: GitHub only.

Usage (from project1/):
    GITHUB_TOKEN=$(gh auth token) uv run python -m merge_docs.cli.validate --repo owner/name --pr 101 --pr 117

For each PR it writes <pr>-comment.md (the comment the app would have posted) and <pr>-<module>.md (the
catalogue page) for each module whose contract changed, and appends one row per PR to summary.csv.
"""
from __future__ import annotations

import argparse
import csv
import os
import tarfile
from pathlib import Path
from typing import Any

import httpx

from merge_docs.core.contract import build_contracts
from merge_docs.core.diff import diff_contracts
from merge_docs.core.notes import notes_path, stale_mentions
from merge_docs.core.render import render_comment, render_module_markdown

COLUMNS = ["pr", "modules_changed", "changes", "endpoints", "declared_response_share", "stale_mentions", "error"]


def _code(files: dict[str, str]) -> dict[str, str]:
    return {p: t for p, t in files.items() if p.endswith(".py")}


def validate_pr(repo: str, pr: int, *, gh: Any, out_dir: Path) -> dict:
    base_sha, head_sha = gh.base_and_head(repo, pr)
    base_files = gh.snapshot(repo, base_sha)
    head_files = base_files if head_sha == base_sha else gh.snapshot(repo, head_sha)
    old = build_contracts(_code(base_files), repo)
    new = build_contracts(_code(head_files), repo)
    changes = diff_contracts(old, new)
    modules = sorted({c.module for c in changes})

    stale: dict[str, list[str]] = {}
    for module in set(new) | set(old):
        note = head_files.get(notes_path(module))
        if note and module in new:
            stale[module] = stale_mentions(note, new, old)

    comment = render_comment(changes, stale, had_changes_before=False) or "No API changes in this PR, so no comment.\n"
    (out_dir / f"{pr}-comment.md").write_text(comment)
    for module in modules:
        if module in new:
            name = f"{pr}-{module.removesuffix('.py').replace('/', '-')}.md"
            (out_dir / name).write_text(render_module_markdown(new[module], head_files.get(notes_path(module))))

    endpoints = [e for c in new.values() for e in c.endpoints]
    declared = sum(1 for e in endpoints if e.response.declared)
    return {"pr": pr, "modules_changed": len(modules), "changes": len(changes), "endpoints": len(endpoints),
            "declared_response_share": f"{declared / len(endpoints):.2f}" if endpoints else "",
            "stale_mentions": sum(len(v) for v in stale.values()), "error": ""}


def run_validation(repo: str, prs: list[int], *, gh: Any, out_dir: Path) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / "summary.csv"
    summary.unlink(missing_ok=True)  # each run replaces the summary, so reruns don't duplicate rows
    new_file = True
    rows = []
    for pr in prs:
        try:
            row = validate_pr(repo, pr, gh=gh, out_dir=out_dir)
        except (httpx.HTTPError, tarfile.TarError, KeyError, ValueError) as err:
            row = {k: "" for k in COLUMNS} | {"pr": pr, "error": f"{type(err).__name__}: {err}"}
        rows.append(row)
        with open(summary, "a", newline="") as f:  # one row at a time, so a later failure keeps earlier rows
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if new_file:
                writer.writeheader()
                new_file = False
            writer.writerow(row)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", type=int, action="append", required=True, help="PR number; repeat for several")
    parser.add_argument("--out", default="validation", help="output folder")
    args = parser.parse_args(argv)

    from merge_docs.adapters.github_read import GitHubReader

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("set GITHUB_TOKEN, e.g. GITHUB_TOKEN=$(gh auth token)")
    for r in run_validation(args.repo, args.pr, gh=GitHubReader(token), out_dir=Path(args.out)):
        status = r["error"] or (f"{r['changes']} change(s) in {r['modules_changed']} module(s), "
                                f"{r['stale_mentions']} stale note mention(s)")
        print(f"PR {r['pr']}: {status}")
    print(f"Wrote results to {args.out}/ (see summary.csv)")


if __name__ == "__main__":
    main()
