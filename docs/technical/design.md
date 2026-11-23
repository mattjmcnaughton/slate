# Slate technical design (v1)

Slate is a single-user task manager that replaces Linear (areas, projects,
status workflow, boards) and Todoist (daily and repeating tasks, natural-language
quick add). Product scope: https://ampcode.com/artifacts/personal-task-manager-v1-scope-9596d145-01a4-41c3-a27a-c3e1c109be05

## Domain

- **Area**: a part of life (Home, Health, Work). Has a name, color, and order.
- **Project**: belongs to an area (optional). Status `planned | active | paused |
  done | canceled`, optional `target_date`, description. Progress counts
  non-repeating, non-canceled tasks: done / total.
- **Task**: global integer id, shown as `SLT-<id>`; the id never changes when the
  task moves. Belongs to a project, or directly to an area, or to neither (Inbox).
  Optional `parent_id` for subtasks, one level deep; subtasks cannot repeat.
  - `status`: `backlog | todo | in_progress | done | canceled`
  - `priority`: 0 none, 1 urgent, 2 high, 3 medium, 4 low (Linear's order)
  - `due_date` (local date) and optional `due_time` (local wall time)
  - optional recurrence: `recurrence_rrule`, `recurrence_mode`
    (`fixed | after_completion`), `recurrence_dtstart`, `recurrence_text`,
    and `completed_runs`
  - labels, comments, an activity log
  - `source` / `source_id`: where an imported record came from, unique together
- **Label**: name and color.
- **Settings**: one row; `timezone` (default `America/New_York`). All dates are
  local to this zone. Timestamps (`created_at`, etc.) are stored in UTC.

## Repeating tasks

A repeating task is one row that rolls forward; it never reaches `done` until
its series ends.

- Completing it logs a `completed_run` activity, increments `completed_runs`,
  and moves `due_date` to `scheduling.next_due(...)`. For fixed rules that is the
  first occurrence after both the old due date and today; missed runs are not
  replayed. For after-completion rules it is completion date + interval.
- When `next_due` returns None (UNTIL or COUNT reached), the task becomes `done`.
- Setting a date on a repeating task, by quick pick or typed date, moves only
  this run. Only a new repeat rule changes the schedule.
- Upcoming shows later runs of fixed rules as ghost items
  (`scheduling.occurrences`). After-completion rules show only their next run.
- Repeating tasks are excluded from project progress and are shown in a
  separate "Recurring" lane on boards.

## Architecture

FastAPI backend in `src/slate`, React frontend in `src/slate/web/frontend`,
built to `dist/` and served by FastAPI in production.

Layering: `routers -> controllers -> services -> repositories`.

- `scheduling/`: pure natural-language parsing and recurrence math. No I/O; all
  functions take `now`/`today` explicitly. Public API in `scheduling/__init__.py`.
- `domain.py`: plain dataclasses for entities, independent of SQLAlchemy.
- `repositories/`: a `UnitOfWork` protocol exposing one repository per aggregate,
  with two implementations:
  - `repositories/sql.py`: SQLAlchemy async; portable column types only, so it
    runs on SQLite and Postgres.
  - `repositories/memory.py`: an in-memory fake with the same behavior.
  A shared contract test suite runs against both (and against Postgres when
  `TEST_POSTGRES_URL` is set), which keeps the fake honest.
- `services/`: business rules (completion and recurrence, agenda building,
  import upserts). Services depend on the `UnitOfWork` and a `Clock`, never on
  globals.
- `deps.py`: the composition root. FastAPI dependencies resolve the clock,
  unit of work, and authenticator from the app's `Container`, which tests and
  dev mode build with fakes.

### Dependency injection and fakes

`create_app(container)` takes a `Container` with:

- `clock`: `SystemClock` in production, `FixedClock` in tests and seeded dev.
- `uow_factory`: SQL or memory.
- `authenticator`: `SessionAuthenticator` (OIDC sign-in with Auth0) in production,
  `DevAuthenticator` (always signed in as a fake user) locally.

No mocks: tests use the memory repositories, the fixed clock, and the dev
authenticator, or the real SQL repositories on a temp SQLite file.

### Local development

`just dev` runs the backend with `SLATE_STORAGE=memory`, `SLATE_AUTH=dev`, and
`SLATE_SEED=demo`, which loads rich sample data (`seed.py`) relative to today:
areas, projects with target dates, Inbox tasks, daily and weekly repeating
tasks, overdue and upcoming tasks, subtasks, labels, comments, and activity.
`just dev-sqlite` persists to `./data.db` instead.

## Database

Postgres in production (Neon, `DATABASE_URL=postgresql+asyncpg://...?ssl=verify-full`,
with `PGSSLROOTCERT` pointing at a CA bundle). SQLite (`sqlite+aiosqlite:///...`)
remains the local default when `DATABASE_URL` is unset.
Alembic migrations use `render_as_batch=True` so they run on SQLite. In
production the app runs migrations on startup.

## HTTP API

JSON under `/api`. Full schema at `/docs` (OpenAPI). Authentication: the browser
uses a signed session cookie set after OIDC sign-in (Auth0); agents and scripts send
`Authorization: Bearer <token>` with a token from `SLATE_API_TOKENS`.

| Method and path | Purpose |
| --- | --- |
| `GET /api/me` | Current user |
| `GET/PATCH /api/settings` | Time zone |
| `GET/POST /api/areas`, `PATCH/DELETE /api/areas/{id}` | Areas |
| `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}` | Projects, with progress |
| `GET/POST /api/labels`, `PATCH/DELETE /api/labels/{id}` | Labels |
| `GET /api/tasks` | Filter: `project_id`, `area_id`, `inbox`, `parent_id`, `status` (repeatable), `priority`, `label_id`, `due_before`, `due_after`, `q`, `include_closed`; sort: `sort=due\|priority\|created\|updated`, `order=asc\|desc` |
| `POST /api/tasks` | Create from fields; `due_string` and `repeat_string` are parsed server-side |
| `POST /api/tasks/quick-add` | Create from one natural-language line |
| `GET/PATCH/DELETE /api/tasks/{ref}` | `ref` is `42` or `SLT-42` |
| `POST /api/tasks/{ref}/complete`, `POST /api/tasks/{ref}/reopen` | Completion rolls repeating tasks forward |
| `GET/POST /api/tasks/{ref}/comments`, `PATCH/DELETE /api/comments/{id}` | Comments |
| `GET /api/tasks/{ref}/activity` | Activity log |
| `GET /api/agenda?start=&end=` | Today/Upcoming: tasks by day, overdue first, with ghost runs |
| `POST /api/parse` | Live quick-add preview: parsed fields and highlight tokens |
| `POST /api/import` | Idempotent bulk upsert by `(source, source_id)` with original timestamps |

## Users

Sign-in upserts a row in `users` keyed by the provider's `(issuer, subject)`, so
each person has a stable local id. Who may sign in is `SLATE_ALLOWED_EMAILS`
(verified emails only). Tasks are not yet scoped per user: everyone allowed in
shares one workspace.

## Deployment

The `slate` deployment on the Amp Box `mattjmcnaughton/apps`, public at
https://slate.mattjmcnaughton.com. The build bundles a relocatable CPython
(python-build-standalone via `uv python install`) and the installed packages,
because Boxes do not guarantee a Python runtime. `.box/run.sh` sets
`PGSSLROOTCERT` to the bundled certifi CA file.

| Piece | Where |
| --- | --- |
| Database | Neon project `slate` (`dark-meadow-34017316`), database `slate`, role `slate_owner`. The app runs migrations at startup. |
| Sign-in | Auth0 application `slate`, callbacks `https://slate.mattjmcnaughton.com/auth/callback` and `https://slate--mattjmcnaughton.onamp.dev/auth/callback`. |
| Plain env (`.amp/box.yaml`) | `SLATE_AUTH=oidc`, `OIDC_ISSUER` (exactly as discovery reports it, with the trailing `/`), `SLATE_PUBLIC_URL`. |
| Secrets | `DATABASE_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `APP_SESSION_SECRET` (32+ chars), `SLATE_API_TOKENS`, `SLATE_ALLOWED_EMAILS` (comma-separated). Stored as `KEY='value'` lines in `secrets.env` in the deployment's data directory (copied with `amp boxes cp`, mode 600), which `.box/run.sh` loads; Amp deployment secrets work too. |

Deploy pushed code with `amp boxes deploy --domain slate.mattjmcnaughton.com`.
Check it with `curl -s https://slate.mattjmcnaughton.com/readyz` and confirm
`/api/tasks` returns 401 without credentials.
