"""Write docs/api.md from the OpenAPI schema: `uv run python scripts/api_docs.py`.

tests/unit/test_api_docs.py fails when the checked-in file is out of date.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "api.md"


def render() -> str:
    from slate.app import DESCRIPTION, create_app
    from slate.auth import DevAuthenticator
    from slate.clock import SystemClock
    from slate.container import Container
    from slate.repositories.memory import MemoryUnitOfWorkFactory

    clock = SystemClock()
    container = Container(clock, MemoryUnitOfWorkFactory(clock), DevAuthenticator())
    schema = create_app(container, serve_frontend=False).openapi()
    lines = [
        "# API reference",
        "",
        "Generated from the OpenAPI schema by `scripts/api_docs.py`; do not edit by hand.",
        "The live schema is at `/openapi.json`, with an interactive version at `/docs`.",
        "",
        DESCRIPTION.strip(),
        "",
        "MCP client setup: [technical/mcp-clients.md](technical/mcp-clients.md).",
    ]
    by_tag: dict[str, list[tuple[str, str, dict]]] = {}
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            tag = (op.get("tags") or ["other"])[0]
            by_tag.setdefault(tag, []).append((method.upper(), path, op))
    for tag in sorted(by_tag):
        lines += [
            "",
            f"## {tag[0].upper()}{tag[1:]}",
            "",
            "| Method | Path | Summary |",
            "| --- | --- | --- |",
        ]
        for method, path, op in by_tag[tag]:
            desc = (op.get("description") or "").strip().split("\n\n")[0].replace("\n", " ")
            summary = op.get("summary", "")
            if desc:
                summary += f": {desc}"
            lines.append(f"| {method} | `{path}` | {summary.replace('|', '\\|')} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.read_text() == text else 1)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
