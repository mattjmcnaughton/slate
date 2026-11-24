"""The sidebar assistant, its settings, and Pending changes.

Settings, the conversation, and applying or dismissing Pending changes need a
browser session: no API key (REST or MCP) can change the Agent mode, edit
AGENT.md, or apply what an agent drafted. REST keys may list Pending changes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from slate.agents.model import provider_label
from slate.deps import BrowserUserDep, ContainerDep, UserDep
from slate.domain import AgentMode, PendingStatus
from slate.repositories.base import NotFoundError
from slate.services import images as image_service
from slate.services.agent import AgentError, AgentTurns, pending_json
from slate.services.tools import ToolContext, ToolError, apply_pending, dismiss_pending

router = APIRouter(prefix="/api")

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in"},
    403: {"description": "Needs a browser session, not an API key"},
}


class AgentSettingsOut(BaseModel):
    enabled: bool = Field(description="Whether the sidebar assistant is on for this workspace.")
    mode: AgentMode = Field(
        description="suggest: agent writes become Pending changes. apply: they run at once "
        "(deletes still wait). Applies to the sidebar and MCP clients."
    )
    instructions: str = Field(description="AGENT.md: standing instructions for the assistant.")
    provider: str = Field(description="Where messages are sent.")
    daily_message_cap: int


class AgentSettingsPatch(BaseModel):
    enabled: bool | None = None
    mode: AgentMode | None = None
    instructions: str | None = Field(default=None, max_length=20_000)


class PendingChangeOut(BaseModel):
    id: UUID
    tool: str = Field(description="The catalog tool that will run, such as save_tasks.")
    origin: Literal["agent", "mcp"]
    status: PendingStatus
    summary: str
    input: dict[str, Any] = Field(description="The tool's arguments; editable before applying.")
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime | None
    resolved_at: datetime | None


class ApplyIn(BaseModel):
    input: dict[str, Any] | None = Field(
        default=None, description="Edited arguments; omit to apply the draft as it is."
    )


class MessageOut(BaseModel):
    id: UUID
    role: Literal["owner", "agent"]
    content: str
    image_count: int
    pending_change_ids: list[str]
    created_at: datetime | None


def _turns(request: Request) -> AgentTurns:
    return request.app.state.agent_turns


def _ctx(container: Any, user: Any) -> ToolContext:
    return ToolContext(container.uow_factory, container.clock, user, "agent")


@router.get(
    "/agent/settings",
    tags=["assistant"],
    response_model=AgentSettingsOut,
    responses=ERRORS,
    summary="Assistant settings",
)
async def get_agent_settings(user: BrowserUserDep, container: ContainerDep) -> AgentSettingsOut:
    async with container.uow_factory(user.workspace_id) as uow:
        s = await uow.settings.get()
    return AgentSettingsOut(
        enabled=s.agent_enabled,
        mode=s.agent_mode,
        instructions=s.agent_instructions,
        provider=provider_label(container.agent_model),
        daily_message_cap=container.agent_daily_message_cap,
    )


@router.patch(
    "/agent/settings",
    tags=["assistant"],
    response_model=AgentSettingsOut,
    responses=ERRORS,
    summary="Change assistant settings",
)
async def patch_agent_settings(
    body: AgentSettingsPatch, user: BrowserUserDep, container: ContainerDep
) -> AgentSettingsOut:
    async with container.uow_factory(user.workspace_id) as uow:
        s = await uow.settings.get()
        if body.enabled is not None:
            s.agent_enabled = body.enabled
        if body.mode is not None:
            s.agent_mode = body.mode
        if body.instructions is not None:
            s.agent_instructions = body.instructions
        await uow.settings.save(s)
        await uow.commit()
    return await get_agent_settings(user, container)


@router.get(
    "/pending-changes",
    tags=["pending changes"],
    response_model=list[PendingChangeOut],
    responses=ERRORS,
    summary="List Pending changes",
)
async def list_pending(
    user: UserDep,
    container: ContainerDep,
    status: Annotated[PendingStatus | Literal["all"], Query()] = PendingStatus.PENDING,
) -> list[dict]:
    """Changes drafted by the assistant or MCP clients. Newest last."""
    async with container.uow_factory(user.workspace_id) as uow:
        rows = await uow.pending_changes.list(None if status == "all" else status)
    return [pending_json(p) for p in rows[-200:]]


@router.post(
    "/pending-changes/{pending_id}/apply",
    tags=["pending changes"],
    response_model=PendingChangeOut,
    responses={
        **ERRORS,
        404: {"description": "No such Pending change"},
        422: {"description": "The input was rejected; the change stays pending"},
    },
    summary="Apply a Pending change",
)
async def apply_pending_change(
    pending_id: UUID, body: ApplyIn, user: BrowserUserDep, container: ContainerDep
) -> dict:
    """Runs the drafted write once. Applying again returns the same result."""
    try:
        return pending_json(await apply_pending(_ctx(container, user), pending_id, body.input))
    except NotFoundError as e:
        raise HTTPException(404, "Pending change not found") from e
    except ToolError as e:
        raise HTTPException(409 if e.code == "conflict" else 422, e.message) from e


@router.post(
    "/pending-changes/{pending_id}/dismiss",
    tags=["pending changes"],
    response_model=PendingChangeOut,
    responses={**ERRORS, 404: {"description": "No such Pending change"}},
    summary="Dismiss a Pending change",
)
async def dismiss_pending_change(
    pending_id: UUID, user: BrowserUserDep, container: ContainerDep
) -> dict:
    try:
        return pending_json(await dismiss_pending(_ctx(container, user), pending_id))
    except NotFoundError as e:
        raise HTTPException(404, "Pending change not found") from e


@router.get(
    "/agent/conversation",
    tags=["assistant"],
    response_model=list[MessageOut],
    responses=ERRORS,
    summary="Your conversation with the assistant",
)
async def get_conversation(user: BrowserUserDep, request: Request) -> list:
    return await _turns(request).read(user)


@router.delete(
    "/agent/conversation",
    tags=["assistant"],
    status_code=204,
    responses=ERRORS,
    summary="Clear your conversation",
)
async def clear_conversation(user: BrowserUserDep, request: Request) -> None:
    """Pending changes it drafted stay listed."""
    await _turns(request).clear(user)


class _Stream(StreamingResponse):
    def __init__(self, content: Any, release: Any) -> None:
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
        self.release = release

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.release()


@router.post(
    "/agent/messages",
    tags=["assistant"],
    responses={
        **ERRORS,
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE: delta, tool, pending_change, applied, done, or error",
        },
        409: {"description": "Assistant off, or a reply is already in progress"},
        422: {"description": "Empty message, or an image was rejected"},
        429: {"description": "Daily cap reached, or the assistant is busy"},
        503: {"description": "The assistant is not configured"},
    },
    summary="Send a message to the assistant",
)
async def send_message(user: BrowserUserDep, request: Request) -> StreamingResponse:
    """Multipart form: ``content`` (text), optional ``screen`` (what the owner is
    looking at), and up to 4 ``images`` (JPEG, PNG, or WebP, 5 MB each). Images
    are re-encoded in memory for this turn and never stored."""
    form = await request.form(
        max_files=image_service.MAX_IMAGES + 1,
        max_fields=10,
        max_part_size=image_service.MAX_IMAGE_BYTES + 1024,
    )
    content = form.get("content") or ""
    screen = form.get("screen") or None
    files = [f for f in form.getlist("images") if not isinstance(f, str)]
    if not isinstance(content, str) or not (screen is None or isinstance(screen, str)):
        raise HTTPException(422, "content and screen must be text")
    raw = [await f.read(image_service.MAX_IMAGE_BYTES + 1) for f in files]
    try:
        normalized = await asyncio.to_thread(image_service.normalize_all, raw)
    except image_service.ImageRejectedError as e:
        raise HTTPException(422, str(e)) from e
    turns = _turns(request)
    try:
        turn = await turns.admit(
            user, content, images=normalized, screen=(screen or "")[:80] or None
        )
    except AgentError as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.message}) from e
    return _Stream(turns.stream(turn), lambda: turns.release(turn))
