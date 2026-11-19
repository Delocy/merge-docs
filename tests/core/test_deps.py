from merge_docs.core.deps import Dependency, read_dependencies

REQUIREMENTS = """\
# web
FastAPI==0.115.0
pydantic[email]==2.9.2 ; python_version >= "3.10"
python_multipart==0.0.6  # forms
uvicorn>=0.30
-r dev.txt
git+https://github.com/acme/thing.git
--index-url https://example.org/simple

"""

PYPROJECT = """\
[project]
name = "shop"
dependencies = [
  "httpx==0.27.0",
  "fastapi>=0.110",
]
"""


def test_requirements_txt_pins_names_and_ranges():
    deps = read_dependencies({"requirements.txt": REQUIREMENTS})
    assert deps == [
        Dependency("fastapi", "0.115.0", "FastAPI==0.115.0", "requirements.txt"),
        Dependency("pydantic", "2.9.2", "pydantic[email]==2.9.2", "requirements.txt"),
        Dependency("python-multipart", "0.0.6", "python_multipart==0.0.6", "requirements.txt"),
        Dependency("uvicorn", None, "uvicorn>=0.30", "requirements.txt"),
    ]


def test_pyproject_dependencies():
    deps = read_dependencies({"pyproject.toml": PYPROJECT})
    assert [(d.name, d.version) for d in deps] == [("fastapi", None), ("httpx", "0.27.0")]


def test_both_files_merge_and_requirements_pin_wins():
    deps = read_dependencies({"requirements.txt": REQUIREMENTS, "pyproject.toml": PYPROJECT})
    fastapi = [d for d in deps if d.name == "fastapi"]
    assert fastapi == [Dependency("fastapi", "0.115.0", "FastAPI==0.115.0", "requirements.txt")]
    assert "httpx" in {d.name for d in deps}


def test_wildcard_pin_counts_as_not_pinned():
    (d,) = read_dependencies({"requirements.txt": "fastapi==0.115.*\n"})
    assert d.version is None


def test_broken_pyproject_is_ignored_not_fatal():
    assert read_dependencies({"pyproject.toml": "[project\nnot toml"}) == []


def test_no_dependency_files():
    assert read_dependencies({"app/main.py": "x = 1"}) == []
