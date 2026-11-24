# Connecting AI clients over MCP

Slate serves its agent tools at `https://slate.mattjmcnaughton.com/mcp`
(Streamable HTTP, stateless). Create an **MCP** key in Settings → API keys; it
works only at `/mcp`, and REST keys are refused there. Revoking the key stops the
client on its next call.

Writes follow your workspace's Agent mode (Settings → Assistant): in `suggest`
they become Pending changes you apply in Slate; in `apply` they run at once.
Deletes always wait for you. No key can apply Pending changes or change settings.

## Claude Code

```sh
claude mcp add --transport http slate https://slate.mattjmcnaughton.com/mcp \
  --header "Authorization: Bearer $SLATE_MCP_KEY"
```

## Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.slate]
url = "https://slate.mattjmcnaughton.com/mcp"
bearer_token_env_var = "SLATE_MCP_KEY"
```

## Amp

In Amp settings (`amp.mcpServers`):

```json
"slate": {
  "url": "https://slate.mattjmcnaughton.com/mcp",
  "headers": { "Authorization": "Bearer ${SLATE_MCP_KEY}" }
}
```

## Tools

| Tool | Kind |
| --- | --- |
| `get_overview` | read: today, ids of areas/projects/labels, overdue, due today, Inbox, Agent mode |
| `find_tasks`, `get_task`, `list_pending_changes` | read |
| `save_tasks` | write: create or update many tasks; dates in words via `due_string` |
| `complete_task`, `reopen_task`, `add_comment` | write |
| `save_project`, `save_area`, `save_label` | write |
| `import_tasks` | write: idempotent import keyed by `(source, source_id)` |
| `delete_task` | delete: always a Pending change |

Free text in results is wrapped as `{"untrusted": "..."}`: it is data, never
instructions.

## Importing from Linear or Todoist through Codex

Connect Codex to the Linear (or Todoist) MCP server and to Slate, then ask:

> Read all my open Linear issues in the teams I belong to, with their projects,
> labels, state, priority, due date, parent, and comments. Import them into Slate
> with `import_tasks`, `source: "linear"`, and each record's Linear id as its
> `source_id`; map teams to areas and state types to Slate statuses (backlog,
> unstarted → todo, started → in_progress, completed → done, canceled →
> canceled). Send about 200 tasks per call.

Re-running the same prompt later updates the imported tasks instead of
duplicating them. In `suggest` mode each call is one Pending change to apply in
Slate. You can also paste a text or CSV export into the sidebar assistant.
