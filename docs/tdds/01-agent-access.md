# 01: Agent access (assistant, MCP, API keys)

Approved by Matt on 2026-11-24 ([plan](https://ampcode.com/artifacts/slate-agent-mcp-api-keys-prd-tdd-draft-6795e4a6-6d8a-457e-9157-6675270e298a)).
Adapted from accanto's [TDD 03](https://github.com/mattjmcnaughton/accanto/blob/main/docs/tdds/03-agent-access.md).
Linear/Todoist API sync was set aside: imports go through agents (`import_tasks`).

## Requirements

- **Sidebar assistant** (Ctrl/Cmd J) that reads and changes the workspace from text and
  images (screenshots, photos of notes). Off until the user turns it on in Settings.
- **One proposal concept.** Agent writes either run (`apply` mode) or become
  **Pending changes** (`suggest` mode, the default) that the owner edits, applies, or
  dismisses. Deletes always pend.
- **MCP** at `/mcp` with the same tools, for `mcp` API keys only. `/api` refuses `mcp`
  keys, so an MCP client cannot use REST to get around `suggest` mode.
- **API keys and OpenAPI**: bearer security scheme, tags, error responses, and a
  generated `docs/api.md`.

## Terms

| Term | Meaning |
| --- | --- |
| Agent mode | Per workspace: `suggest` or `apply`. Applies to the sidebar and MCP. |
| Pending change | A validated write (`tool` + `input`) waiting for the owner. |
| AGENT.md | The owner's standing instructions for the sidebar; trusted, below enforced rules. |
| Untrusted | Free text from data (titles, names, comments, imports, images). Serialized `{"untrusted": "..."}`. |

## Design as built

| Module | Role |
| --- | --- |
| `dtos/tools.py` | `Untrusted`, tool inputs, explicit projections (`extra="forbid"`). |
| `services/tools.py` | The 13-tool catalog and `call_tool`, which enforces the mode on the server; `apply_pending`, `dismiss_pending`. |
| `mcp_server.py` | FastMCP 4.1.0, stateless Streamable HTTP, `MountMCP` ahead of routing, `KeyVerifier` (mcp keys only, re-checked per request). |
| `agents/sidebar.py`, `agents/model.py` | pydantic-ai agent with no bound model; OpenRouter with `zdr: true, data_collection: deny`, or `stub` (refused on a public HTTPS origin). |
| `services/agent.py`, `routers/agent.py` | Turns: admit (stores the owner message, so failed turns count toward the daily cap), stream (SSE `delta`, `tool`, `pending_change`, `applied`, `done`, `error`, `: ping`), settle. |
| `services/images.py` | Magic bytes, 5 MB, 40 MP cap, re-encode to JPEG ≤1568 px. Runs after auth, in a worker thread. Never stored. |
| `web/frontend/src/components/Assistant.tsx`, `routes/pending.tsx` | Panel, editable cards, Pending changes page; Settings → Assistant. |

Tools: `get_overview` (the combined read), `find_tasks`, `get_task`,
`list_pending_changes`, `save_tasks` (batched; `due_string` resolved when drafted),
`complete_task`, `reopen_task`, `delete_task`, `add_comment`, `save_project`,
`save_area`, `save_label`, `import_tasks`. Excluded: keys, settings, AGENT.md, applying
Pending changes, deleting projects/areas/labels.

Data (migration `0005_agent_access`, additive): `workspaces.agent_enabled`,
`agent_mode`, `agent_instructions`; `pending_changes`; `agent_messages`. Applying is
`UPDATE … WHERE status='pending'`, so it happens once.

Limits: 12 model requests and 120 s per turn, 2 concurrent replies (`429 agent_busy`),
one reply per user (`409`), 200 messages a day per user (`AGENT_DAILY_MESSAGE_CAP`),
history of 10 turns as plain text, conversations expire 30 days after the last turn.
Logs carry tool names, timings, and token counts only.

Config: `AGENT_MODEL` (default `openai/gpt-6-luna`), `OPENROUTER_API_KEY` (secret).

## Deviations from accanto

- In `apply` mode sidebar writes really apply (accanto always pends sidebar writes).
- Agent settings live on the workspace row; conversations are one message list per user.
- The daily cap counts attempts; images are validated after auth off the event loop.
- `mcp` keys are a separate kind from the start (accanto's open gap).

## Verification

- `tests/unit/test_tools_untrusted.py`: every projection's free text is `Untrusted`.
- `tests/integration/test_agent.py`: key kinds on `/mcp` and `/api`, exact tool list,
  revocation, suggest vs apply, deletes pend, apply once with edits, workspace
  isolation, sidebar SSE with the stub model, images, daily cap, stub refusal.
- `tests/integration/test_repository_contract.py`: memory, SQLite, and Postgres agree.
- Manual run against `openai/gpt-6-luna` with a real email screenshot (demo video).
