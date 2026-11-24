# API reference

Generated from the OpenAPI schema by `scripts/api_docs.py`; do not edit by hand.
The live schema is at `/openapi.json`, with an interactive version at `/docs`.

Slate's JSON API. Every record belongs to your workspace; ids are UUIDs, and task
routes also accept keys such as `SLT-12`. Another workspace's id answers 404.

**Authentication.** Browsers use the session cookie set at sign-in. Scripts send
`Authorization: Bearer <key>` with a **REST** key from Settings → API keys (use
*Authorize* above). Keys act as you, in your workspace, and revoking one takes
effect on the next request. Keys cannot manage keys, change settings, change the
assistant, or apply Pending changes: those need a browser session.

**MCP.** AI clients (Claude Code, Codex, Amp) connect to `/mcp` (Streamable HTTP)
with an **MCP** key. MCP keys work only there, and REST keys are refused there.
The MCP tools are the same 13 the sidebar assistant uses.

**Agent mode.** Writes from the assistant and MCP clients follow your workspace's
Agent mode: `suggest` stores them as Pending changes for you to apply, `apply`
runs them at once. Deletes always wait for you.

MCP client setup: [technical/mcp-clients.md](technical/mcp-clients.md).

## Account

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/me` | Me |
| GET | `/api/settings` | Get Settings |
| PATCH | `/api/settings` | Patch Settings |

## Agenda

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/agenda` | Agenda |

## Api keys

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/api-keys` | List Api Keys |
| POST | `/api/api-keys` | Create Api Key |
| DELETE | `/api/api-keys/{key_id}` | Revoke Api Key |

## Areas

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/areas` | List Areas |
| POST | `/api/areas` | Create Area |
| PATCH | `/api/areas/{area_id}` | Patch Area |
| DELETE | `/api/areas/{area_id}` | Delete Area |

## Assistant

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/agent/settings` | Assistant settings |
| PATCH | `/api/agent/settings` | Change assistant settings |
| GET | `/api/agent/conversation` | Your conversation with the assistant |
| DELETE | `/api/agent/conversation` | Clear your conversation: Pending changes it drafted stay listed. |
| POST | `/api/agent/messages` | Send a message to the assistant: Multipart form: ``content`` (text), optional ``screen`` (what the owner is looking at), and up to 4 ``images`` (JPEG, PNG, or WebP, 5 MB each). Images are re-encoded in memory for this turn and never stored. |

## Auth

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/auth/signin` | Signin |
| GET | `/auth/callback` | Callback |
| POST | `/auth/signout` | Signout: End Slate's session and the provider's, so the next sign-in can pick an account. |

## Comments

| Method | Path | Summary |
| --- | --- | --- |
| PATCH | `/api/comments/{comment_id}` | Patch Comment |
| DELETE | `/api/comments/{comment_id}` | Delete Comment |

## Health

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/healthz` | Healthz: Liveness probe. |
| GET | `/readyz` | Readyz: Readiness probe: the storage answers a query. |

## Import

| Method | Path | Summary |
| --- | --- | --- |
| POST | `/api/import` | Import Batch: Idempotent bulk upsert keyed by (source, source_id) within your workspace. Safe to re-run. |

## Labels

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/labels` | List Labels |
| POST | `/api/labels` | Create Label |
| PATCH | `/api/labels/{label_id}` | Patch Label |
| DELETE | `/api/labels/{label_id}` | Delete Label |

## Pending changes

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/pending-changes` | List Pending changes: Changes drafted by the assistant or MCP clients. Newest last. |
| POST | `/api/pending-changes/{pending_id}/apply` | Apply a Pending change: Runs the drafted write once. Applying again returns the same result. |
| POST | `/api/pending-changes/{pending_id}/dismiss` | Dismiss a Pending change |

## Projects

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/projects` | List Projects |
| POST | `/api/projects` | Create Project |
| GET | `/api/projects/{project_id}` | Get Project |
| PATCH | `/api/projects/{project_id}` | Patch Project |
| DELETE | `/api/projects/{project_id}` | Delete Project |

## Tasks

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/tasks` | List Tasks |
| POST | `/api/tasks` | Create Task |
| POST | `/api/tasks/quick-add` | Quick Add |
| GET | `/api/tasks/{ref}` | Get Task |
| PATCH | `/api/tasks/{ref}` | Patch Task |
| DELETE | `/api/tasks/{ref}` | Delete Task |
| POST | `/api/tasks/{ref}/complete` | Complete Task |
| POST | `/api/tasks/{ref}/reopen` | Reopen Task |
| GET | `/api/tasks/{ref}/comments` | List Comments |
| POST | `/api/tasks/{ref}/comments` | Add Comment |
| GET | `/api/tasks/{ref}/activity` | List Activity |
| POST | `/api/parse` | Parse |
