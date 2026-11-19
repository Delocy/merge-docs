"""The action and the example workflows must be valid YAML with the shape GitHub expects."""
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def test_action_yml_parses_and_is_composite():
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    assert set(action["inputs"]) >= {"command", "token"}
    assert all("shell" in s for s in action["runs"]["steps"] if "run" in s)


def test_example_workflows_parse_and_use_the_action():
    for name in ["api-changes.yml", "catalogue.yml"]:
        wf = yaml.safe_load((ROOT / "examples" / name).read_text())
        uses = [s.get("uses", "") for job in wf["jobs"].values() for s in job.get("steps", [])]
        assert any(u.startswith("Delocy/merge-docs@") for u in uses), name
