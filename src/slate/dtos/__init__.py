"""Pydantic request and response models for the HTTP API.

Patch models distinguish "not sent" from "sent as null" via ``model_fields_set``:
sending ``"due_date": null`` clears the date, leaving it out keeps it.
"""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field

from slate.domain import ProjectStatus, TaskStatus


class Model(BaseModel):
    model_config = {"from_attributes": True}


# --- shared --------------------------------------------------------------------


class UserOut(Model):
    id: str
    name: str
    email: str | None
    via: str


class SettingsOut(Model):
    timezone: str


class SettingsPatch(Model):
    timezone: str


class RecurrenceOut(Model):
    rrule: str
    mode: str
    dtstart: date
    time: time | None
    text: str


# --- areas, projects, labels -----------------------------------------------------


class AreaIn(Model):
    name: str = Field(min_length=1, max_length=200)
    color: str = "#6b7280"
    position: int = 0


class AreaPatch(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = None
    position: int | None = None


class AreaOut(Model):
    id: int
    name: str
    color: str
    position: int


class ProjectIn(Model):
    name: str = Field(min_length=1, max_length=200)
    area_id: int | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str = ""
    target_date: date | None = None
    color: str | None = None
    position: int = 0


class ProjectPatch(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    area_id: int | None = None
    status: ProjectStatus | None = None
    description: str | None = None
    target_date: date | None = None
    color: str | None = None
    position: int | None = None


class ProjectOut(Model):
    id: int
    name: str
    area_id: int | None
    status: ProjectStatus
    description: str
    target_date: date | None
    color: str | None
    position: int
    progress_done: int = 0
    progress_total: int = 0
    open_count: int = 0
    created_at: datetime
    updated_at: datetime


class LabelIn(Model):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#6b7280"


class LabelPatch(Model):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = None


class LabelOut(Model):
    id: int
    name: str
    color: str


# --- tasks -----------------------------------------------------------------------


class TaskIn(Model):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = Field(default=0, ge=0, le=4)
    project_id: int | None = None
    area_id: int | None = None
    parent_id: int | None = None
    label_ids: list[int] = []
    due_date: date | None = None
    due_time: time | None = None
    due_string: str | None = Field(
        default=None,
        description="Natural-language date or repeat, such as 'next fri 5pm' or 'every weekday'. "
        "Overrides due_date and due_time.",
    )


class TaskPatch(Model):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=0, le=4)
    project_id: int | None = None
    area_id: int | None = None
    parent_id: int | None = None
    label_ids: list[int] | None = None
    due_date: date | None = None
    due_time: time | None = None
    due_string: str | None = Field(
        default=None,
        description="Natural-language date or repeat. A date moves only this run of a "
        "repeating task; a repeat ('every mon') replaces the schedule.",
    )
    clear_recurrence: bool = False


class TaskOut(Model):
    id: int
    key: str
    title: str
    description: str
    status: TaskStatus
    priority: int
    project_id: int | None
    area_id: int | None
    parent_id: int | None
    label_ids: list[int]
    due_date: date | None
    due_time: time | None
    recurrence: RecurrenceOut | None
    completed_runs: int
    completed_at: datetime | None
    comment_count: int = 0
    subtask_count: int = 0
    open_subtask_count: int = 0
    source: str | None
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class CompleteOut(Model):
    task: TaskOut
    open_subtasks: int = Field(
        description="Open subtasks left behind; the UI warns when this is nonzero."
    )


class CommentIn(Model):
    body: str = Field(min_length=1)


class CommentOut(Model):
    id: int
    task_id: int
    body: str
    created_at: datetime
    updated_at: datetime


class ActivityOut(Model):
    id: int
    task_id: int
    kind: str
    data: dict
    created_at: datetime


# --- parsing ---------------------------------------------------------------------


class ParseIn(Model):
    text: str


class TokenOut(Model):
    kind: str
    start: int
    end: int
    text: str
    unresolved: bool


class ParseOut(Model):
    title: str
    due_date: date | None
    due_time: time | None
    recurrence: RecurrenceOut | None
    area_id: int | None
    project_id: int | None
    unknown_project: str | None
    label_ids: list[int]
    unknown_labels: list[str]
    priority: int | None
    status: str | None
    tokens: list[TokenOut]


class QuickAddIn(Model):
    text: str = Field(min_length=1)
    create_missing: bool = Field(
        default=False,
        description="Create an unknown #project or @label instead of dropping it.",
    )
    # Defaults applied when the text does not say otherwise, e.g. from the current view.
    project_id: int | None = None
    area_id: int | None = None
    parent_id: int | None = None


# --- agenda ----------------------------------------------------------------------


class GhostOut(Model):
    task_id: int
    date: date


class AgendaDayOut(Model):
    date: date
    tasks: list[TaskOut]
    ghosts: list[GhostOut]


class AgendaOut(Model):
    today: date
    overdue: list[TaskOut]
    days: list[AgendaDayOut]


# --- import ----------------------------------------------------------------------


class ImportCommentIn(Model):
    source_id: str
    body: str
    created_at: datetime | None = None


class ImportAreaIn(Model):
    source_id: str
    name: str
    color: str | None = None
    position: int = 0


class ImportProjectIn(Model):
    source_id: str
    name: str
    area_source_id: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str = ""
    target_date: date | None = None
    created_at: datetime | None = None


class ImportLabelIn(Model):
    source_id: str
    name: str
    color: str | None = None


class ImportTaskIn(Model):
    source_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = Field(default=0, ge=0, le=4, description="0 none, 1 urgent ... 4 low")
    project_source_id: str | None = None
    area_source_id: str | None = None
    parent_source_id: str | None = None
    label_source_ids: list[str] = []
    due_date: date | None = None
    due_time: time | None = None
    repeat: str | None = Field(
        default=None, description="Free-text repeat rule, such as Todoist's due.string."
    )
    created_at: datetime | None = None
    completed_at: datetime | None = None
    comments: list[ImportCommentIn] = []


class ImportIn(Model):
    source: str = Field(min_length=1, max_length=32, description="Such as 'todoist' or 'linear'.")
    areas: list[ImportAreaIn] = []
    projects: list[ImportProjectIn] = []
    labels: list[ImportLabelIn] = []
    tasks: list[ImportTaskIn] = []


class ImportOut(Model):
    created: dict[str, int]
    updated: dict[str, int]
    warnings: list[str]
