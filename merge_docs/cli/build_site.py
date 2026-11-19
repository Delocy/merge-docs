"""Build the static catalogue for GitHub Pages from a checkout.

Usage (in CI, from the repo root):
    python -m merge_docs.cli.build_site --repo-dir . --repo "$GITHUB_REPOSITORY" --out site --changes 10

With GITHUB_TOKEN set, the "API changes" page is rebuilt from the last N merged PRs through the GitHub API.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from merge_docs.core.contract import build_contracts
from merge_docs.core.deps import read_dependencies
from merge_docs.core.diff import diff_contracts
from merge_docs.core.notes import notes_path
from merge_docs.core.site import MergedChanges, build_site

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "site", "__pycache__", ".github"}


def read_checkout(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not path.is_file():
            continue
        if (path.suffix == ".py" or (rel.parts[:2] == ("docs", "features") and path.suffix == ".md")
                or rel.as_posix() in ("requirements.txt", "pyproject.toml")):
            files[rel.as_posix()] = path.read_text(errors="replace")
    return files


def merged_changes(repo: str, gh, limit: int, base: str | None = None) -> list[MergedChanges]:
    out = []
    for pr in gh.recent_merged_prs(repo, limit, base=base):
        base, head = gh.base_and_head(repo, pr["number"])
        old = build_contracts(_code(gh.snapshot(repo, base)), repo)
        new = build_contracts(_code(gh.snapshot(repo, head)), repo)
        changes = diff_contracts(old, new)
        if changes:
            out.append(MergedChanges(pr["number"], pr["title"], pr["html_url"], (pr["merged_at"] or "")[:10], tuple(changes)))
    return out


def _code(files: dict[str, str]) -> dict[str, str]:
    return {p: t for p, t in files.items() if p.endswith(".py")}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--repo", required=True, help="owner/name, shown on the site and used for links")
    parser.add_argument("--out", default="site")
    parser.add_argument("--changes", type=int, default=10, help="how many recent merged PRs to scan (needs GITHUB_TOKEN)")
    parser.add_argument("--base", default=os.environ.get("GITHUB_REF_NAME"), help="only PRs merged into this branch")
    args = parser.parse_args(argv)

    files = read_checkout(Path(args.repo_dir))
    contracts = build_contracts(_code(files), args.repo)
    notes = {m: files[notes_path(m)] for m in contracts if notes_path(m) in files}
    changes: list[MergedChanges] = []
    token = os.environ.get("GITHUB_TOKEN")
    if token and args.changes > 0:
        from merge_docs.adapters.github_read import GitHubReader
        changes = merged_changes(args.repo, GitHubReader(token), args.changes, base=args.base)
    deps = read_dependencies(files)
    written = build_site(contracts, notes, changes, args.repo, Path(args.out), deps=deps)
    print(f"Built {len(written)} files for {len(contracts)} feature(s) into {args.out}/ "
          f"({len(changes)} merged PR(s) with API changes, {len(deps)} dependencies)")


if __name__ == "__main__":
    main()
