"""Which model the sidebar assistant runs on.

``AGENT_MODEL`` is an OpenRouter model id, routed only to zero-data-retention
endpoints, or ``stub`` for a deterministic test model that never leaves the
process. The stub is refused when Slate is served from a public HTTPS origin.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from urllib.parse import urlsplit

from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

STUB = "stub"
# Zero-data-retention endpoints only. A provider 5xx is retried, then OpenRouter
# falls back to the next model (also ZDR-routed) instead of failing the turn.
FALLBACK = "anthropic/claude-haiku-5.5"
ZDR = OpenRouterModelSettings(
    openrouter_provider={"zdr": True, "data_collection": "deny"},
    max_retries=2,
)
_cache: dict[tuple[str, str], Model] = {}


class AgentUnavailableError(Exception):
    """The assistant cannot run with this configuration; the message is safe to show."""


def resolve_model(model_id: str, api_key: str, public_url: str = "") -> Model:
    model_id = model_id.strip()
    if not model_id:
        raise AgentUnavailableError("The assistant is not configured (AGENT_MODEL).")
    if model_id == STUB:
        origin = urlsplit(public_url)
        if origin.scheme == "https" and origin.hostname not in ("localhost", "127.0.0.1"):
            raise AgentUnavailableError("AGENT_MODEL=stub is for tests only.")
        return stub_model()
    if not api_key:
        raise AgentUnavailableError("The assistant is not configured (OPENROUTER_API_KEY).")
    model = _cache.get((model_id, api_key))
    if model is None:
        settings = OpenRouterModelSettings(**ZDR)
        if model_id != FALLBACK:
            settings["openrouter_models"] = [FALLBACK]
        model = OpenRouterModel(
            model_id, provider=OpenRouterProvider(api_key=api_key), settings=settings
        )
        _cache[(model_id, api_key)] = model
    return model


def provider_label(model_id: str) -> str:
    if model_id == STUB:
        return "Test model (nothing leaves Slate)"
    if not model_id:
        return "Not configured"
    return f"{model_id} through OpenRouter, zero-data-retention endpoints only"


# --- the stub -------------------------------------------------------------------------
#
# Reads the owner's latest message and this run's tool results, then calls real
# tools. Behaviors (case-insensitive):
# - lines starting with "- ": get_overview, then save_tasks with one task per line;
#   "#name" on a line files it in the project with that name.
# - an attached image: save_tasks with one task, "Task from image".
# - "complete SLT-n" / "delete SLT-n": that tool.
# - "[stub-fail]": fail after a few words.
# - anything else: a short fixed reply.


def _prompt(messages: Sequence[ModelMessage]) -> tuple[str, bool]:
    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart):
                if isinstance(part.content, str):
                    return part.content, False
                text = " ".join(c for c in part.content if isinstance(c, str))
                return text, any(isinstance(c, BinaryContent) for c in part.content)
    return "", False


def _returns(messages: Sequence[ModelMessage]) -> list[ToolReturnPart]:
    parts = [p for m in messages if isinstance(m, ModelRequest) for p in m.parts]
    start = max((i for i, p in enumerate(parts) if isinstance(p, UserPromptPart)), default=-1)
    return [p for p in parts[start + 1 :] if isinstance(p, ToolReturnPart)]


def _content(part: ToolReturnPart) -> dict:
    value = part.content
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _call(name: str, args: dict) -> DeltaToolCalls:
    return {0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=f"stub-{name}")}


def _untrusted(value: object) -> str:
    return value.get("untrusted", "") if isinstance(value, dict) else str(value or "")


async def _stub(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    text, image = _prompt(messages)
    returns = _returns(messages)
    done = {r.tool_name: _content(r) for r in returns}
    lowered = text.lower()
    if "[stub-fail]" in lowered:
        yield "Starting"
        raise RuntimeError("stub failure")
    items = [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]
    if items:
        if "get_overview" not in done:
            yield _call("get_overview", {})
            return
        if "save_tasks" not in done:
            projects = {
                _untrusted(p["name"]).lower(): p["id"]
                for p in done["get_overview"].get("projects", [])
            }
            tasks = []
            for item in items:
                fields: dict = {}
                match = re.search(r"#([\w-]+(?: [\w-]+)*)$", item)
                if match and match.group(1).lower() in projects:
                    fields["project_id"] = projects[match.group(1).lower()]
                    item = item[: match.start()].strip()
                tasks.append({"title": item, **fields})
            yield _call("save_tasks", {"tasks": tasks})
            return
        yield f"I drafted {len(items)} task(s)."
        return
    if image:
        if "save_tasks" not in done:
            yield _call("save_tasks", {"tasks": [{"title": "Task from image"}]})
            return
        yield "I read one to-do from the image."
        return
    for verb in ("complete", "delete"):
        match = re.search(rf"{verb} (SLT-\d+)", text, re.IGNORECASE)
        if match:
            tool = f"{verb}_task"
            if tool not in done:
                yield _call(tool, {"ref": match.group(1).upper()})
                return
            yield f"Done: {_untrusted(done[tool].get('summary'))}."
            return
    yield "I can read and change your tasks. "
    yield "Ask me to add, move, or complete something."


def stub_model() -> FunctionModel:
    return FunctionModel(stream_function=_stub, model_name="stub")
