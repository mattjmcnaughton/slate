"""Sidebar assistant turns: admit, stream, settle.

``admit`` checks everything before the first byte: the assistant is on, the
daily cap, one reply per user at a time, and the process-wide reply limit. It
stores the owner's message at once, so the daily cap counts attempts and a
failing turn cannot be retried around it. ``stream`` runs the agent with the
model injected and yields SSE frames; each tool call opens its own short unit
of work. ``settle`` stores the reply.

Logs hold tool names, timings, token counts, and error codes only: never
prompts, replies, task text, or images.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from pydantic_ai import UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.run import AgentRunResultEvent

from slate.agents.model import AgentUnavailableError, resolve_model
from slate.agents.sidebar import SidebarDeps, build_sidebar_agent
from slate.domain import AgentMessage
from slate.services.tasks import TaskService
from slate.services.tools import ToolContext, call_tool

if TYPE_CHECKING:
    from slate.auth import User
    from slate.container import Container
    from slate.domain import PendingChange

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
log = structlog.get_logger(__name__)

REQUEST_LIMIT = 12
REPLY_TIMEOUT = 120.0
HEARTBEAT = 15.0
MAX_MESSAGE = 200_000  # pasted exports can be long
HISTORY_TURNS = 10
RETENTION = timedelta(days=30)
CONCURRENT_REPLIES = 2


class AgentError(Exception):
    """Refused before streaming; routers map ``status`` to HTTP."""

    def __init__(self, code: str, message: str, status: int) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def pending_json(p: PendingChange) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "tool": p.tool,
        "origin": p.origin,
        "status": str(p.status),
        "summary": p.summary,
        "input": p.input,
        "result": p.result,
        "error": p.error,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
    }


@dataclass
class Turn:
    user: User
    content: str
    images: list[bytes] = field(default_factory=list)
    screen: str | None = None
    deps: dict[str, Any] = field(default_factory=dict)
    history: list[ModelMessage] = field(default_factory=list)


class AgentTurns:
    """One per app: holds in-flight users and the reply limit."""

    def __init__(self, container: Container) -> None:
        self.c = container
        self.in_flight: set[Any] = set()
        self.replies = asyncio.Semaphore(CONCURRENT_REPLIES)
        self.agent = build_sidebar_agent()

    def model(self) -> Any:
        c = self.c
        return resolve_model(c.agent_model, c.openrouter_api_key, c.public_url)

    async def _expire(self, uow: Any, user: User) -> list[AgentMessage]:
        messages = await uow.agent_messages.list_for_user(user.id)
        last = messages[-1].created_at if messages else None
        if last and last < self.c.clock.now() - RETENTION:
            await uow.agent_messages.clear(user.id)
            return []
        return messages

    async def admit(
        self, user: User, content: str, *, images: list[bytes], screen: str | None
    ) -> Turn:
        content = content.strip()
        if not content and not images:
            raise AgentError("empty_message", "Write a message first.", 422)
        if len(content) > MAX_MESSAGE:
            raise AgentError("message_too_long", "That message is too long.", 422)
        try:
            self.model()
        except AgentUnavailableError as e:
            raise AgentError("agent_unavailable", str(e), 503) from None
        if user.id in self.in_flight:
            raise AgentError("reply_in_progress", "Wait for the current reply to finish.", 409)
        if self.replies.locked():
            raise AgentError("agent_busy", "The assistant is busy. Try again in a moment.", 429)
        self.in_flight.add(user.id)
        try:
            return await self._admit(user, content, images, screen)
        except BaseException:
            self.in_flight.discard(user.id)
            raise

    async def _admit(
        self, user: User, content: str, images: list[bytes], screen: str | None
    ) -> Turn:
        now = self.c.clock.now()
        async with self.c.uow_factory(user.workspace_id) as uow:
            settings = await uow.settings.get()
            if not settings.agent_enabled:
                raise AgentError("agent_disabled", "Turn on the assistant in Settings.", 409)
            messages = await self._expire(uow, user)
            sent = sum(
                1
                for m in messages
                if m.role == "owner" and m.created_at and m.created_at >= now - timedelta(days=1)
            )
            if sent >= self.c.agent_daily_message_cap:
                raise AgentError(
                    "daily_cap_reached", "The daily message limit is reached. Try tomorrow.", 429
                )
            await uow.agent_messages.add(
                AgentMessage(
                    user_id=user.id, role="owner", content=content, image_count=len(images)
                )
            )
            today = await TaskService(uow, self.c.clock).today()
            await uow.commit()
        return Turn(
            user=user,
            content=content,
            images=images,
            screen=screen,
            deps={
                "user_name": user.name,
                "timezone": settings.timezone,
                "today": today,
                "mode": str(settings.agent_mode),
                "agent_md": settings.agent_instructions,
            },
            history=_history(messages),
        )

    def release(self, turn: Turn) -> None:
        self.in_flight.discard(turn.user.id)

    async def stream(self, turn: Turn) -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        producer = asyncio.create_task(self._produce(turn, queue))
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if frame is None:
                    return
                yield frame
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer

    async def _produce(self, turn: Turn, queue: asyncio.Queue) -> None:
        started = time.perf_counter()
        try:
            async with self.replies:
                text, pending, usage = await self._run(turn, queue)
            async with self.c.uow_factory(turn.user.workspace_id) as uow:
                saved = await uow.agent_messages.add(
                    AgentMessage(
                        user_id=turn.user.id,
                        role="agent",
                        content=text,
                        pending_change_ids=pending,
                    )
                )
                await uow.commit()
            await queue.put(
                sse("done", {"message_id": str(saved.id), "pending_change_ids": pending})
            )
            log.info(
                "agent_turn",
                outcome="success",
                ms=round((time.perf_counter() - started) * 1000),
                **usage,
            )
        except AgentError as e:
            log.warning("agent_turn", outcome="failure", code=e.code)
            await queue.put(sse("error", {"code": e.code, "message": e.message}))
        except asyncio.CancelledError:
            log.info("agent_turn", outcome="stopped")
            raise
        except Exception as e:
            log.warning("agent_turn", outcome="failure", error=type(e).__name__)
            await queue.put(
                sse(
                    "error",
                    {"code": "internal_error", "message": "The reply did not come through."},
                )
            )
        finally:
            await queue.put(None)

    async def _run(self, turn: Turn, queue: asyncio.Queue) -> tuple[str, list[str], dict]:
        pending: list[str] = []
        ctx = ToolContext(self.c.uow_factory, self.c.clock, turn.user, "agent")

        async def call(name: str, arguments: dict) -> dict:
            await queue.put(sse("tool", {"name": name, "status": "started"}))
            started = time.perf_counter()
            try:
                result = await call_tool(ctx, name, arguments)
            except Exception:
                log.info("agent_tool", tool=name, outcome="rejected")
                await queue.put(sse("tool", {"name": name, "status": "failed"}))
                raise
            log.info("agent_tool", tool=name, ms=round((time.perf_counter() - started) * 1000))
            payload = result.model_dump(mode="json")
            await queue.put(sse("tool", {"name": name, "status": "done"}))
            if payload.get("outcome") == "pending":
                async with self.c.uow_factory(turn.user.workspace_id) as uow:
                    for pid in payload["pending_change_ids"]:
                        p = await uow.pending_changes.get(UUID(pid))
                        if p is not None:
                            pending.append(pid)
                            await queue.put(sse("pending_change", pending_json(p)))
            elif payload.get("outcome") == "applied":
                await queue.put(
                    sse(
                        "applied",
                        {
                            "tool": name,
                            "summary": payload["summary"]["untrusted"],
                            "tasks": payload.get("tasks", []),
                        },
                    )
                )
            return payload

        deps = SidebarDeps(**turn.deps, call=call, screen=turn.screen, image_count=len(turn.images))
        prompt: list[Any] = [turn.content or "Please look at the attached image(s)."]
        prompt += [BinaryContent(data=img, media_type="image/jpeg") for img in turn.images]
        text: str | None = None
        usage: dict = {}
        try:
            async with (
                asyncio.timeout(REPLY_TIMEOUT),
                self.agent.run_stream_events(
                    prompt,
                    deps=deps,
                    message_history=turn.history,
                    model=self.model(),
                    usage_limits=UsageLimits(request_limit=REQUEST_LIMIT),
                ) as events,
            ):
                async for event in events:
                    delta = _text_of(event)
                    if delta:
                        await queue.put(sse("delta", {"text": delta}))
                    elif isinstance(event, AgentRunResultEvent):
                        text = str(event.result.output)
                        u = event.result.usage
                        usage = {
                            "requests": u.requests,
                            "input_tokens": u.input_tokens,
                            "output_tokens": u.output_tokens,
                        }
        except TimeoutError:
            raise AgentError("timeout", "The reply took too long. Try again.", 504) from None
        except UsageLimitExceeded:
            raise AgentError(
                "too_many_steps", "That needed too many steps. Try a narrower request.", 422
            ) from None
        except Exception as e:
            log.warning("agent_model_failed", error=type(e).__name__)
            raise AgentError("upstream_error", "The model did not answer.", 502) from None
        if text is None:
            raise AgentError("upstream_error", "The model did not answer.", 502)
        return text, pending, usage

    async def read(self, user: User) -> list[AgentMessage]:
        async with self.c.uow_factory(user.workspace_id) as uow:
            messages = await self._expire(uow, user)
            await uow.commit()
            return messages

    async def clear(self, user: User) -> None:
        async with self.c.uow_factory(user.workspace_id) as uow:
            await uow.agent_messages.clear(user.id)
            await uow.commit()


def _history(messages: list[AgentMessage]) -> list[ModelMessage]:
    """Earlier turns as plain text: an owner message and the reply that answered it."""
    pairs: list[tuple[AgentMessage, AgentMessage]] = []
    for prev, cur in zip(messages, messages[1:], strict=False):
        if prev.role == "owner" and cur.role == "agent":
            pairs.append((prev, cur))
    out: list[ModelMessage] = []
    for owner, agent in pairs[-HISTORY_TURNS:]:
        note = f"\n[{owner.image_count} image(s) were attached]" if owner.image_count else ""
        out.append(ModelRequest(parts=[UserPromptPart(content=owner.content + note)]))
        out.append(ModelResponse(parts=[TextPart(content=agent.content)]))
    return out


def _text_of(event: Any) -> str:
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        return event.part.content
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return event.delta.content_delta
    return ""
