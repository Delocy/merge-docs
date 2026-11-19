from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_api"


def sample_files() -> dict[str, str]:
    return {str(p.relative_to(FIXTURE)): p.read_text() for p in FIXTURE.rglob("*.py")}
