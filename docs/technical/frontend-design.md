# Slate frontend design brief

One design system that merges two prototypes: **Ledger** (dense, dark,
Linear-like) and **Daybook** (calm, light, serif planner).

- **Structure is Ledger's everywhere on desktop:** a left sidebar (Today,
  Upcoming, Inbox, All tasks, then areas with their projects nested), one-line
  task rows, a detail pane that opens beside the list, and a slim bottom "mode
  line" that shows the keys for the selected task.
- **Light theme (default) uses Daybook's palette.** Today and Upcoming use
  Daybook's serif headline treatment (the date as the headline, a short
  sub-line), with the quick-add line right under it.
- **Dark theme is Ledger's palette.** Toggle in the sidebar footer and the ⌘K
  palette; remember it in localStorage; default to the OS preference.
- **Phone (≤ 640px):** Daybook's single column, a bottom tab bar (Today,
  Upcoming, Inbox, Projects, All), a floating add button, the detail as a full
  screen sheet, swipe right to complete, swipe left to open a date picker
  (Tomorrow, This weekend, Next week, plus a typed date).

## Tokens

Light (Daybook):
`--bg:#f4f6f1 --panel:#fff --ink:#1a2320 --ink2:#55615b --ink3:#87918b
--line:#e1e6de --line2:#c9d1c8 --accent:#1d6b55 --accent-soft:#e0eee7
--red:#b3304d --amber:#a86a12 --blue:#2c68ad --plum:#7a4bb0`
Serif for headlines: `Newsreader, "Iowan Old Style", "Palatino Linotype", Georgia, serif`
(self-host Newsreader via @fontsource/newsreader or fall back to Georgia).

Dark (Ledger):
`--bg:#14161b --panel:#181b21 --raise:#1f232b --hover:#232832 --line:#262a33
--line2:#343a48 --ink:#e3e5ea --ink2:#a0a6b4 --ink3:#6d7382 --accent:#8d95f7
--accent-soft:rgba(141,149,247,.16) --amber:#eab254 --red:#ef7b7e --teal:#62c6bd
--plum:#c596e8`. In dark mode headlines stay sans (Inter/system), 13px base,
tabular numbers.

UI text: `Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
`kbd` chips: monospace 10.5px, raised border-bottom 2px.

## Status and priority

Statuses: backlog, todo, in_progress, done, canceled, each with a small
Linear-style circle icon (dashed, empty, half, check, x). Priority 0 none,
1 urgent (red), 2 high, 3 medium, 4 low, shown as signal bars like Linear.
Task keys like `SLT-42` in the dim color at the row start (desktop only).

## Keyboard

Global: `⌘K`/`Ctrl+K` palette, `c` quick add, `/` search (palette in search
mode), `?` shortcut sheet, `g t` Today, `g u` Upcoming, `g i` Inbox, `g a` All
tasks, `g p` Projects, `Esc` closes the top layer.
In lists: `j`/`k` move, `Enter` open, `x` select (multi), `e` complete,
`s` status menu, `p` priority menu, `d` due (typed natural language),
`l` labels, `v` switch list/board on project pages, `Backspace`/`Delete` delete
with confirm. Menus open at the selected row and take digit keys.
Never fire single-key shortcuts while typing in an input or textarea.

## Behaviors that come from the backend rules

- Quick add calls `POST /api/parse` as you type (debounced ~120ms) and
  highlights token spans from `tokens` over the input; the preview shows the
  parsed date, repeat text, project/area, labels, priority, status. An
  unresolved `#name` shows "Create project 'name'" (send
  `create_missing: true`). Default project/area comes from the current page.
- Completing a repeating task does not remove it: it moves to its next date
  (show a toast "Next: Tue, Nov 24" with Undo = reopen is not available for
  runs, so no undo for runs). For a parent with open subtasks, the complete
  response includes `open_subtasks`; show a warning toast.
- Upcoming shows ghost runs (`ghosts` in `/api/agenda`) faded, not
  interactive except opening the real task.
- Boards: columns Backlog / Todo / In progress / Done / Canceled, plus a
  separate "Recurring" lane at the top or side for tasks with a recurrence.
  Drag a card between columns to PATCH its status; repeating cards cannot be
  dragged into Done.
- Project header shows the target date and progress done/total (repeating
  tasks excluded by the API).
- Task detail: title (editable), description (Markdown textarea with preview),
  properties (status, priority, project/area, labels, due with natural-language
  input, repeat text), subtasks with inline add, comments (add, edit, delete),
  and an activity timeline merged with comments by time.
- All tasks: a table with filters (area, project, status multi, priority,
  label, due range presets and custom from/to, text search) and sort (due,
  priority, created, updated; asc/desc), with filters in the URL search params.
- Settings: time zone select (`PATCH /api/settings`).

## Auth

`GET /api/me` 401 → full-page redirect to
`/auth/signin?return_to=<current path>`. Sign out is `POST /auth/signout`.
