"""Known security advisories for exact package versions, from the OSV.dev API (free, no key)."""
from __future__ import annotations

import httpx

from merge_docs.core.deps import Dependency

URL = "https://api.osv.dev/v1/querybatch"


def query_advisories(deps: list[Dependency], transport: httpx.BaseTransport | None = None) -> dict[str, list[str]]:
    """name -> advisory ids for each pinned dependency (one batch request). Raises httpx.HTTPError on failure."""
    pinned = [d for d in deps if d.version]
    if not pinned:
        return {}
    with httpx.Client(timeout=30, transport=transport, headers={"User-Agent": "merge-docs"}) as client:
        r = client.post(URL, json={"queries": [{"package": {"name": d.name, "ecosystem": "PyPI"}, "version": d.version}
                                               for d in pinned]})
        r.raise_for_status()
        results = r.json()["results"]
    return {d.name: [v["id"] for v in (res.get("vulns") or [])] for d, res in zip(pinned, results)}
