import runpy
from pathlib import Path


def test_api_docs_are_current():
    script = Path(__file__).resolve().parents[2] / "scripts" / "api_docs.py"
    mod = runpy.run_path(str(script))
    assert mod["OUT"].read_text() == mod["render"](), "run: uv run python scripts/api_docs.py"


def test_openapi_declares_bearer_auth_and_tags():
    mod = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "api_docs.py"))
    text = mod["render"]()
    for tag in ("## Tasks", "## Pending changes", "## Assistant", "## Api keys"):
        assert tag in text
