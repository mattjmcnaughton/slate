"""Every free-text field an agent reads is marked Untrusted (TDD: define it first)."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from slate.dtos import tools as t

# str fields that are not free text: keys, enum-like codes, timestamps.
SAFE = {
    ("TaskRow", "key"),
    ("TaskRow", "parent_key"),
    ("TaskDetail", "key"),
    ("TaskDetail", "parent_key"),
    ("CommentRow", "created_at"),
    ("PendingRow", "tool"),
    ("PendingRow", "origin"),
    ("PendingRow", "status"),
    ("Overview", "timezone"),
    ("Overview", "agent_mode"),
    ("WriteResult", "outcome"),
    ("WriteResult", "detail"),  # counter names such as created_tasks
}


def _projections() -> list[type[BaseModel]]:
    return [
        v
        for v in vars(t).values()
        if isinstance(v, type) and issubclass(v, t.Out) and v is not t.Out
    ]


def _plain_str(annotation: object) -> bool:
    if annotation is str:
        return True
    if typing.get_origin(annotation) is typing.Annotated:
        base, *meta = typing.get_args(annotation)
        return t.UNTRUSTED not in meta and _plain_str(base)
    return any(_plain_str(a) for a in typing.get_args(annotation) if a is not type(None))


def test_free_text_in_every_projection_is_untrusted():
    for model in _projections():
        for name, info in model.model_fields.items():
            if t.UNTRUSTED in info.metadata or (model.__name__, name) in SAFE:
                continue
            assert not _plain_str(info.annotation), f"{model.__name__}.{name} is plain str"


def test_untrusted_serializes_as_a_marked_object():
    row = t.LabelRow(id="01a20e0f-df0a-7296-a81f-f75e1220c2a8", name="ignore previous")
    assert row.model_dump(mode="json")["name"] == {"untrusted": "ignore previous"}
