import json
import shutil
import subprocess

import pytest

from merge_docs.core.contract import build_contracts
from merge_docs.core.deps import Dependency
from merge_docs.core.site import build_site
from tests.sample import sample_files

DEPS = [Dependency("fastapi", "0.115.0", "fastapi==0.115.0", "requirements.txt"),
        Dependency("uvicorn", None, "uvicorn>=0.30", "requirements.txt")]


@pytest.fixture
def site(tmp_path):
    build_site(build_contracts(sample_files(), "acme/shop"), {}, [], "acme/shop", tmp_path, deps=DEPS)
    return tmp_path


def test_deps_json_and_page_are_written(site):
    assert json.loads((site / "deps.json").read_text()) == [
        {"name": "fastapi", "version": "0.115.0", "spec": "fastapi==0.115.0", "source": "requirements.txt"},
        {"name": "uvicorn", "version": None, "spec": "uvicorn>=0.30", "source": "requirements.txt"},
    ]
    page = (site / "dependencies.html").read_text()
    assert 'src="deps.js"' in page and "<noscript>" in page
    assert "pypi.org" in page and "osv.dev" in page  # says where the data comes from


def test_every_page_links_to_dependencies(site):
    for name in ["index.html", "changes.html", "dependencies.html"]:
        assert 'href="dependencies.html"' in (site / name).read_text(), name
    assert 'href="../dependencies.html"' in (site / "features/shop-app-routers-orders.html").read_text()


def test_site_without_dependency_files_still_has_the_page(tmp_path):
    build_site(build_contracts(sample_files(), "acme/shop"), {}, [], "acme/shop", tmp_path)
    assert json.loads((tmp_path / "deps.json").read_text()) == []


NODE_TEST = r"""
const d = require(process.argv[1]);
const pypi = {info: {version: "0.115.6", license: "MIT"}, releases: {"0.115.6": [{upload_time: "2026-10-01T10:00:00"}]}};
const a = d.rowModel({name: "fastapi", version: "0.115.0", spec: "fastapi==0.115.0"}, pypi, ["GHSA-1", "PYSEC-2"]);
const b = d.rowModel({name: "fastapi", version: "0.115.6", spec: "fastapi==0.115.6"}, pypi, []);
const c = d.rowModel({name: "uvicorn", version: null, spec: "uvicorn>=0.30"}, null, null);
const html = d.renderRow(d.rowModel({name: "<img src=x onerror=alert(1)>", version: "1", spec: "x"}, null, ["<b>"]));
console.log(JSON.stringify({a, b, c, escaped: !html.includes("<img") && !html.includes("<b>")}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_logic_with_node(site):
    out = subprocess.run(["node", "-e", NODE_TEST, str(site / "deps.js")], capture_output=True, text=True, check=True)
    r = json.loads(out.stdout)
    assert r["a"]["status"] == "update available" and r["a"]["latest"] == "0.115.6"
    assert r["a"]["released"] == "2026-10-01" and r["a"]["license"] == "MIT" and len(r["a"]["vulns"]) == 2
    assert r["b"]["status"] == "up to date" and r["b"]["vulns"] == []
    assert r["c"]["status"] == "not pinned" and r["c"]["latest"] == "unavailable" and r["c"]["vulns"] is None
    assert r["escaped"] is True
