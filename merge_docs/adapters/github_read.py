"""Read-only GitHub access: a PR's base and head commits, its changed files, and a code snapshot."""
from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass

import httpx

API = "https://api.github.com"


@dataclass(frozen=True)
class ChangedFile:
    filename: str
    status: str
    patch: str


def _keep(path: str) -> bool:
    return path.endswith(".py") or (path.startswith("docs/features/") and path.endswith(".md"))


class GitHubReader:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "merge-docs"},
            transport=transport, follow_redirects=True, timeout=60,
        )

    def base_and_head(self, repo: str, pr: int) -> tuple[str, str]:
        r = self.client.get(f"/repos/{repo}/pulls/{pr}")
        r.raise_for_status()
        data = r.json()
        base, head = data["base"]["sha"], data["head"]["sha"]
        # Compare against the merge base, so commits that landed on the base branch later don't show up as changes.
        c = self.client.get(f"/repos/{repo}/compare/{base}...{head}")
        c.raise_for_status()
        return c.json()["merge_base_commit"]["sha"], head

    def pr_files(self, repo: str, pr: int) -> list[ChangedFile]:
        out: list[ChangedFile] = []
        page = 1
        while True:
            r = self.client.get(f"/repos/{repo}/pulls/{pr}/files", params={"per_page": 100, "page": page})
            r.raise_for_status()
            batch = r.json()
            out += [ChangedFile(f["filename"], f["status"], f.get("patch", "")) for f in batch]
            if len(batch) < 100:
                return out
            page += 1

    def snapshot(self, repo: str, sha: str) -> dict[str, str]:
        r = self.client.get(f"/repos/{repo}/tarball/{sha}")
        r.raise_for_status()
        files: dict[str, str] = {}
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                path = member.name.split("/", 1)[1] if "/" in member.name else member.name
                if not _keep(path):
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                files[path] = handle.read().decode("utf-8", errors="replace")
        return files

    # ----- used by the GitHub Actions commands -----

    def recent_merged_prs(self, repo: str, limit: int, base: str | None = None, max_pages: int = 5) -> list[dict]:
        """The latest `limit` PRs merged into `base`, newest merge first (scans up to max_pages * 100 closed PRs)."""
        merged: list[dict] = []
        params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100}
        if base:
            params["base"] = base
        for page in range(1, max_pages + 1):
            r = self.client.get(f"/repos/{repo}/pulls", params={**params, "page": page})
            r.raise_for_status()
            batch = r.json()
            merged += [p for p in batch if p.get("merged_at")]
            if len(batch) < 100:
                break
        return sorted(merged, key=lambda p: p["merged_at"], reverse=True)[:limit]

    def issue_comments(self, repo: str, pr: int) -> list[dict]:
        out, page = [], 1
        while True:
            r = self.client.get(f"/repos/{repo}/issues/{pr}/comments", params={"per_page": 100, "page": page})
            r.raise_for_status()
            batch = r.json()
            out += [{"id": c["id"], "body": c.get("body") or "", "user": (c.get("user") or {}).get("login"),
                     "user_type": (c.get("user") or {}).get("type")} for c in batch]
            if len(batch) < 100:
                return out
            page += 1

    def create_comment(self, repo: str, pr: int, body: str) -> int:
        r = self.client.post(f"/repos/{repo}/issues/{pr}/comments", json={"body": body})
        r.raise_for_status()
        return r.json()["id"]

    def update_comment(self, repo: str, comment_id: int, body: str) -> None:
        r = self.client.patch(f"/repos/{repo}/issues/comments/{comment_id}", json={"body": body})
        r.raise_for_status()
