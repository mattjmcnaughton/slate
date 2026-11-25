// An in-memory stand-in for the Slate HTTP API, so stories render the real
// components and screens without a backend. Data mirrors src/slate/seed.py,
// dated relative to today. Writes (complete, edit, quick add) change the
// in-memory data, so stories stay interactive until the story reloads.

import type {
  Activity,
  Agenda,
  AgentMessage,
  ApiKey,
  Area,
  Comment,
  Label,
  ParseResult,
  PendingChange,
  Project,
  Recurrence,
  Task,
  TaskStatus,
  Token,
} from "../lib/api";
import { addDays, diffDays, weekday } from "../lib/dates";

/** demo: seeded data; empty: a new account; loading: reads never answer; error: the server is down. */
export type Scenario = "demo" | "empty" | "loading" | "error";

interface Db {
  areas: Area[];
  projects: Project[];
  labels: Label[];
  tasks: Task[];
  comments: Comment[];
  activity: Activity[];
  pending: PendingChange[];
  conversation: AgentMessage[];
  apiKeys: ApiKey[];
  seq: number;
}

/** UUID-shaped ids that keep the seed's short numbers readable: tid(10) is task SLT-10. */
const uuid = (kind: number, n: number) =>
  `00000000-0000-4000-800${kind}-${String(n).padStart(12, "0")}`;
export const tid = (n: number) => uuid(1, n);
export const pid = (n: number) => uuid(2, n);
export const aid = (n: number) => uuid(3, n);
export const lid = (n: number) => uuid(4, n);
const oid = (n: number) => uuid(5, n);

function localToday(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const today = localToday();
const d = (n: number) => addDays(today, n);
const ago = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString();
const nextWeekday = (dow: number) => d((dow - weekday(today) + 7) % 7);

function rec(rrule: string, text: string, time: string | null = null): Recurrence {
  const mode = text.startsWith("every!") ? "after_completion" : "fixed";
  return { rrule, mode, dtstart: today, time, text };
}

function task(id: number, title: string, extra: Partial<Task> = {}): Task {
  return {
    id: tid(id),
    number: id,
    key: `SLT-${id}`,
    title,
    description: "",
    status: "todo",
    priority: 0,
    project_id: null,
    area_id: null,
    parent_id: null,
    parent_key: null,
    label_ids: [],
    due_date: null,
    due_time: null,
    recurrence: null,
    completed_runs: 0,
    completed_at: null,
    comment_count: 0,
    subtask_count: 0,
    open_subtask_count: 0,
    source: null,
    source_id: null,
    created_at: ago(24 * 5 + id),
    updated_at: ago(id),
    ...extra,
  };
}

function project(id: number, name: string, area: number, extra: Partial<Project>): Project {
  return {
    id: pid(id),
    name,
    area_id: aid(area),
    status: "active",
    description: "",
    target_date: null,
    color: null,
    position: id,
    progress_done: 0,
    progress_total: 0,
    open_count: 0,
    created_at: ago(24 * 30),
    updated_at: ago(24),
    ...extra,
  };
}

function demo(): Db {
  const firstOfMonth = (() => {
    const [y, m] = today.split("-").map(Number);
    const next = new Date(Date.UTC(y, m, 1));
    return next.toISOString().slice(0, 10);
  })();
  const tasks: Task[] = [
    task(1, "Call the dentist to reschedule", { due_date: d(0), priority: 2, label_ids: [lid(2)] }),
    task(2, "Return library books", { due_date: d(-2), label_ids: [lid(1)] }),
    task(3, "Look into a standing desk", { description: "Budget around $500." }),
    task(4, "Buy birthday card for Sam", { due_date: d(3), label_ids: [lid(1), lid(4)] }),
    task(5, "Pay rent", {
      area_id: aid(1),
      priority: 1,
      due_date: firstOfMonth,
      recurrence: rec("FREQ=MONTHLY;BYMONTHDAY=1", "every 1st"),
    }),
    task(6, "Take out recycling", {
      area_id: aid(1),
      label_ids: [lid(4)],
      due_date: nextWeekday(2),
      recurrence: rec("FREQ=WEEKLY;BYDAY=TU", "every tue"),
    }),
    task(7, "Water the ferns", {
      area_id: aid(1),
      due_date: d(1),
      recurrence: rec("FREQ=DAILY;INTERVAL=3", "every! 3 days"),
    }),
    task(8, "Stretch", {
      area_id: aid(2),
      due_date: d(0),
      due_time: "07:00:00",
      recurrence: rec("FREQ=DAILY", "every day", "07:00:00"),
      completed_runs: 12,
    }),
    task(9, "Weekly review", {
      priority: 3,
      due_date: d(4),
      comment_count: 1,
      recurrence: rec("FREQ=WEEKLY", "every week"),
    }),
    task(10, "Pick backsplash tile", {
      project_id: pid(1),
      status: "in_progress",
      priority: 2,
      due_date: d(2),
      comment_count: 2,
      subtask_count: 2,
      open_subtask_count: 1,
      description:
        "Two finalists:\n\n- **White zellige**: warmer, ships Monday\n- **Green subway**: 3 weeks out\n\nGrout in a warm gray either way.",
    }),
    task(11, "Order tile samples", {
      project_id: pid(1),
      parent_id: tid(10),
      parent_key: "SLT-10",
      status: "done",
      completed_at: ago(30),
    }),
    task(12, "Measure the backsplash area", {
      project_id: pid(1),
      parent_id: tid(10),
      parent_key: "SLT-10",
      due_date: d(1),
      label_ids: [lid(4)],
    }),
    task(13, "Buy paint and rollers", { project_id: pid(1), due_date: d(-1), label_ids: [lid(1)] }),
    task(14, "Paint the walls", { project_id: pid(1), due_date: d(6) }),
    task(15, "Swap the faucet", { project_id: pid(1), status: "backlog" }),
    task(16, "Get a plumber quote", {
      project_id: pid(1),
      status: "done",
      label_ids: [lid(2)],
      completed_at: ago(50),
    }),
    task(17, "Replace cabinet handles", { project_id: pid(1), status: "canceled" }),
    task(18, "Buy new running shoes", {
      project_id: pid(2),
      status: "done",
      completed_at: ago(80),
    }),
    task(19, "Register for the race", { project_id: pid(2), priority: 1, due_date: d(5) }),
    task(20, "Find a training plan", { project_id: pid(2), status: "in_progress" }),
    task(21, "Long run", {
      project_id: pid(2),
      due_date: nextWeekday(0),
      recurrence: rec("FREQ=WEEKLY;BYDAY=SU", "every sun"),
    }),
    task(22, "Easy run", {
      project_id: pid(2),
      due_date: nextWeekday(2),
      recurrence: rec("FREQ=WEEKLY;BYDAY=TU", "every tue"),
    }),
    task(23, "Book a sports massage", { project_id: pid(2), status: "backlog" }),
    task(24, "Draft the Q1 roadmap", {
      project_id: pid(3),
      status: "in_progress",
      priority: 1,
      due_date: d(1),
      label_ids: [lid(3)],
      comment_count: 1,
    }),
    task(25, "Headcount request", { project_id: pid(3), priority: 2, due_date: d(4) }),
    task(26, "Offsite agenda", { project_id: pid(3), due_date: d(8) }),
    task(27, "Collect team input", { project_id: pid(3), status: "done", completed_at: ago(26) }),
    task(28, "1:1 with Priya", {
      project_id: pid(3),
      due_date: d(0),
      due_time: "14:30:00",
      label_ids: [lid(2)],
    }),
    task(29, "Natural-language parser", {
      project_id: pid(4),
      status: "in_progress",
      priority: 1,
      label_ids: [lid(3)],
    }),
    task(30, "Import from Todoist", { project_id: pid(4), due_date: d(7) }),
    task(31, "Import from Linear", { project_id: pid(4), due_date: d(9) }),
    task(32, "MCP server", { project_id: pid(4), status: "backlog" }),
    task(33, "Deploy to an Amp Box", { project_id: pid(4), status: "done", completed_at: ago(40) }),
    task(34, "Clean out the garage", {
      area_id: aid(1),
      status: "backlog",
      created_at: "2025-11-01T12:00:00Z",
    }),
    task(35, "Send the November invoice", {
      area_id: aid(3),
      due_date: d(0),
      status: "done",
      completed_at: ago(2),
    }),
  ];
  const comments: Comment[] = [
    [9, "Check Upcoming, then each active project's board.", 30],
    [10, "Narrowed to the white zellige or the green subway.", 48],
    [10, "Green subway is 3 weeks out; zellige ships Monday.", 20],
    [24, "Start from last quarter's retro notes.", 6],
  ].map(([task_id, body, h], i) => ({
    id: oid(i + 1),
    task_id: tid(task_id as number),
    body: body as string,
    created_at: ago(h as number),
    updated_at: ago(h as number),
  }));
  const activity: Activity[] = tasks.map((t) => ({
    id: t.id,
    task_id: t.id,
    kind: "created",
    data: {},
    created_at: t.created_at,
  }));
  activity.push(
    {
      id: oid(100),
      task_id: tid(10),
      kind: "status",
      data: { field: "status", from: "todo", to: "in_progress" },
      created_at: ago(40),
    },
    {
      id: oid(101),
      task_id: tid(10),
      kind: "updated",
      data: { field: "priority", from: 3, to: 2 },
      created_at: ago(36),
    },
  );
  return {
    areas: [
      { id: aid(1), name: "Home", color: "#d97706", position: 0 },
      { id: aid(2), name: "Health", color: "#16a34a", position: 1 },
      { id: aid(3), name: "Work", color: "#2563eb", position: 2 },
      { id: aid(4), name: "Side projects", color: "#9333ea", position: 3 },
    ],
    labels: [
      { id: lid(1), name: "errand", color: "#f59e0b" },
      { id: lid(2), name: "calls", color: "#06b6d4" },
      { id: lid(3), name: "deep-work", color: "#6366f1" },
      { id: lid(4), name: "quick", color: "#84cc16" },
    ],
    projects: [
      project(1, "Kitchen refresh", 1, {
        description: "Paint, new backsplash, and swap the faucet before the holidays.",
        target_date: d(24),
      }),
      project(2, "Half marathon", 2, {
        description: "Spring half. Build to 20 miles a week by February.",
        target_date: d(120),
      }),
      project(3, "Q1 planning", 3, {
        description: "Roadmap, headcount ask, and the offsite agenda.",
        target_date: d(10),
      }),
      project(4, "Slate", 4, {
        description: "This app. Replace Linear and Todoist.",
        target_date: d(40),
      }),
      project(5, "Garden beds", 1, {
        status: "planned",
        description: "Raised beds along the fence, next spring.",
        target_date: d(150),
      }),
    ],
    tasks,
    comments,
    activity,
    ...assistantData(),
    seq: 1000,
  };
}

/** A short assistant exchange that drafted changes, plus keys, for the assistant and Settings. */
function assistantData() {
  const change = (
    n: number,
    tool: string,
    summary: string,
    input: Record<string, unknown>,
    status: PendingChange["status"] = "pending",
    origin: PendingChange["origin"] = "agent",
  ): PendingChange => ({
    id: uuid(7, n),
    tool,
    origin,
    status,
    summary,
    input,
    result: null,
    error: null,
    created_at: ago(1),
    resolved_at: status === "pending" ? null : ago(0.5),
  });
  const pending = [
    change(1, "save_tasks", "Move “Return library books” to Saturday", {
      tasks: [{ ref: "SLT-2", due_date: nextWeekday(6) }],
    }),
    change(2, "save_tasks", "New task: Pick up tile at the hardware store", {
      tasks: [{ title: "Pick up tile at the hardware store", project_id: pid(1), priority: 2 }],
    }),
    change(3, "delete_task", "Delete SLT-17 “Replace cabinet handles”", { ref: "SLT-17" }),
    change(
      4,
      "save_tasks",
      "Add 3 tasks to Q1 planning",
      { tasks: [{}, {}, {}] },
      "applied",
      "mcp",
    ),
  ];
  const msg = (n: number, role: AgentMessage["role"], content: string, ids: string[] = []) => ({
    id: uuid(8, n),
    role,
    content,
    image_count: 0,
    pending_change_ids: ids,
    created_at: ago(1),
  });
  const conversation: AgentMessage[] = [
    msg(1, "owner", "What's overdue, and what should I push to the weekend?"),
    msg(
      2,
      "agent",
      "Two things are overdue: **Return library books** and **Buy paint and rollers**. The library run fits Saturday, so I drafted that move, plus a task to pick up the tile while you're out. I also drafted deleting the canceled cabinet-handles task.",
      pending.slice(0, 3).map((p) => p.id),
    ),
  ];
  const apiKeys: ApiKey[] = [
    {
      id: uuid(6, 1),
      name: "Claude Desktop",
      kind: "mcp",
      created_at: ago(24 * 6),
      last_used_at: ago(3),
      revoked_at: null,
    },
    {
      id: uuid(6, 2),
      name: "Shortcuts on iPhone",
      kind: "rest",
      created_at: ago(24 * 20),
      last_used_at: ago(30),
      revoked_at: null,
    },
  ];
  return { pending, conversation, apiKeys };
}

const emptyDb = (): Db => ({
  areas: [],
  projects: [],
  labels: [],
  tasks: [],
  comments: [],
  activity: [],
  pending: [],
  conversation: [],
  apiKeys: [],
  seq: 1,
});

let scenario: Scenario = "demo";
let db: Db = demo();

/** Reset the data for a story. */
export function resetMockApi(s: Scenario) {
  scenario = s;
  db = s === "empty" ? emptyDb() : demo();
}

const closed = (s: TaskStatus) => s === "done" || s === "canceled";
const clone = <T>(v: T): T => structuredClone(v);

function projectsWithProgress(): Project[] {
  return db.projects.map((p) => {
    const own = db.tasks.filter((t) => t.project_id === p.id && !t.recurrence && !t.parent_id);
    const counted = own.filter((t) => t.status !== "canceled");
    return {
      ...p,
      progress_total: counted.length,
      progress_done: counted.filter((t) => t.status === "done").length,
      open_count: own.filter((t) => !closed(t.status)).length,
    };
  });
}

function withCounts(t: Task): Task {
  const subs = db.tasks.filter((s) => s.parent_id === t.id);
  return {
    ...t,
    subtask_count: subs.length,
    open_subtask_count: subs.filter((s) => !closed(s.status)).length,
    comment_count: db.comments.filter((c) => c.task_id === t.id).length,
  };
}

const ORDER: Record<string, (t: Task) => string | number> = {
  due: (t) => `${t.due_date ?? "9999"}${t.due_time ?? ""}`,
  priority: (t) => (t.priority === 0 ? 9 : t.priority),
  created: (t) => t.created_at,
  updated: (t) => t.updated_at,
  position: (t) => t.number,
};

function listTasks(q: URLSearchParams): Task[] {
  const str = (k: string) => q.get(k) ?? undefined;
  const statuses = q.getAll("status");
  const priorities = q.getAll("priority").map(Number);
  const parent = str("parent_id");
  let list = db.tasks.filter((t) => {
    if (str("project_id") !== undefined && t.project_id !== str("project_id")) return false;
    if (str("area_id") !== undefined) {
      const area = t.project_id
        ? db.projects.find((p) => p.id === t.project_id)?.area_id
        : t.area_id;
      if (area !== str("area_id")) return false;
    }
    if (q.get("inbox") === "true" && (t.project_id || t.area_id || t.parent_id)) return false;
    if (q.get("top_level") === "true" && t.parent_id) return false;
    if (parent && t.parent_id !== parent) return false;
    if (statuses.length) {
      if (!statuses.includes(t.status)) return false;
    } else if (q.get("include_closed") !== "true" && closed(t.status)) return false;
    if (priorities.length && !priorities.includes(t.priority)) return false;
    if (str("label_id") !== undefined && !t.label_ids.includes(str("label_id") as string))
      return false;
    const before = q.get("due_before");
    const after = q.get("due_after");
    if (before && (!t.due_date || t.due_date > before)) return false;
    if (after && (!t.due_date || t.due_date < after)) return false;
    if (q.get("has_due") === "true" && !t.due_date) return false;
    if (q.get("has_due") === "false" && t.due_date) return false;
    if (q.get("recurring") === "true" && !t.recurrence) return false;
    const text = q.get("q")?.toLowerCase();
    if (text && !t.title.toLowerCase().includes(text)) return false;
    return true;
  });
  const key = ORDER[q.get("sort") ?? "due"] ?? ORDER.due;
  list = [...list].sort((a, b) =>
    key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : a.number - b.number,
  );
  if (q.get("order") === "desc") list.reverse();
  const limit = Number(q.get("limit") ?? 0);
  return (limit ? list.slice(0, limit) : list).map(withCounts);
}

/** Days between runs, for ghost rows on Upcoming; null when there are none to draw. */
function step(r: Recurrence): number | null {
  if (r.mode === "after_completion") return null;
  if (r.rrule.startsWith("FREQ=DAILY")) return Number(/INTERVAL=(\d+)/.exec(r.rrule)?.[1] ?? 1);
  if (r.rrule.startsWith("FREQ=WEEKLY")) return 7;
  return null;
}

function agenda(start = today, end = addDays(start, 13)): Agenda {
  const top = db.tasks.filter((t) => !t.parent_id).map(withCounts);
  const days = [];
  for (let date = start; date <= end; date = addDays(date, 1)) {
    const ghosts = top
      .filter((t) => t.recurrence && t.due_date && date > t.due_date && !closed(t.status))
      .filter((t) => {
        const s = step(t.recurrence as Recurrence);
        return s !== null && diffDays(date, t.due_date as string) % s === 0;
      })
      .map((t) => ({ task_id: t.id, date }));
    days.push({
      date,
      tasks: top.filter((t) => t.due_date === date && t.status !== "canceled"),
      ghosts,
    });
  }
  const overdue =
    start === today ? top.filter((t) => t.due_date && t.due_date < today && !closed(t.status)) : [];
  return { today, overdue, days };
}

// --- quick-add parsing (a small subset of the server's grammar) ---------------------

const WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const SIGIL = /(?<!\S)(?:#([\w-]+)|@([\w-]+)|\/([\w-]+)|(p[1-4]))(?=[.,;:!?)]*(?:\s|$))/gi;
const WORD =
  /(?<!\S)(every (?:day|week|mon|tue|wed|thu|fri|sat|sun)|today|tomorrow|tmr|mon|tue|wed|thu|fri|sat|sun|\d{1,2}(?::\d{2})?(?:am|pm))(?!\S)/gi;
const STATUS: Record<string, TaskStatus> = {
  backlog: "backlog",
  todo: "todo",
  doing: "in_progress",
  done: "done",
};
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

function parse(text: string): ParseResult {
  const out: ParseResult = {
    title: "",
    due_date: null,
    due_time: null,
    recurrence: null,
    area_id: null,
    project_id: null,
    unknown_project: null,
    label_ids: [],
    unknown_labels: [],
    priority: null,
    status: null,
    tokens: [],
  };
  const token = (m: RegExpExecArray, kind: string, unresolved = false): Token => ({
    kind,
    start: m.index,
    end: m.index + m[0].length,
    text: m[0],
    unresolved,
  });
  for (const m of text.matchAll(SIGIL)) {
    const [, proj, label, status, pri] = m;
    if (proj) {
      const p = db.projects.find((x) => slug(x.name).startsWith(slug(proj)));
      const a = p ? undefined : db.areas.find((x) => slug(x.name).startsWith(slug(proj)));
      if (p) out.project_id = p.id;
      else if (a) out.area_id = a.id;
      else out.unknown_project = proj;
      out.tokens.push(token(m, "project"));
    } else if (label) {
      const l = db.labels.find((x) => slug(x.name) === slug(label));
      if (l) out.label_ids.push(l.id);
      else out.unknown_labels.push(label);
      out.tokens.push(token(m, "label"));
    } else if (status) {
      const s = STATUS[status.toLowerCase()];
      if (s) out.status = s;
      out.tokens.push(token(m, "status", !s));
    } else if (pri) {
      out.priority = Number(pri[1]) === 4 ? 0 : Number(pri[1]);
      out.tokens.push(token(m, "priority"));
    }
  }
  for (const m of text.matchAll(WORD)) {
    const w = m[0].toLowerCase();
    if (w.startsWith("every")) {
      const unit = w.slice(6);
      const dow = WEEKDAYS.indexOf(unit);
      out.recurrence = rec(
        dow >= 0
          ? `FREQ=WEEKLY;BYDAY=${unit.slice(0, 2).toUpperCase()}`
          : `FREQ=${unit === "day" ? "DAILY" : "WEEKLY"}`,
        w,
      );
      out.due_date = dow >= 0 ? nextWeekday(dow) : today;
      out.tokens.push(token(m, "recurrence"));
    } else if (/\d/.test(w)) {
      const [, h, min = "00", ampm] = /(\d{1,2})(?::(\d{2}))?(am|pm)/.exec(w) ?? [];
      const hour = (Number(h) % 12) + (ampm === "pm" ? 12 : 0);
      out.due_time = `${String(hour).padStart(2, "0")}:${min}:00`;
      out.due_date ??= today;
      out.tokens.push(token(m, "date"));
    } else {
      const dow = WEEKDAYS.indexOf(w);
      out.due_date = w === "today" ? today : dow >= 0 ? nextWeekday(dow) : d(1);
      if (dow >= 0 && out.due_date === today) out.due_date = d(7);
      out.tokens.push(token(m, "date"));
    }
  }
  let title = text;
  for (const t of [...out.tokens].sort((a, b) => b.start - a.start)) {
    title = title.slice(0, t.start) + title.slice(t.end);
  }
  out.title = title.replace(/\s+/g, " ").trim();
  return out;
}

// --- request routing ------------------------------------------------------------------

class Reply {
  constructor(
    readonly status: number,
    readonly body?: unknown,
  ) {}
}

function findTask(ref: string): Task {
  const t = db.tasks.find((x) => x.id === ref || x.key === ref);
  if (!t) throw new Reply(404, { detail: "Task not found" });
  return t;
}

function save(t: Task, patch: Partial<Task>): Task {
  Object.assign(t, patch, { updated_at: new Date().toISOString() });
  return withCounts(t);
}

function create(fields: Partial<Task> & { title: string }): Task {
  const t = task(++db.seq, fields.title, { created_at: new Date().toISOString(), ...fields });
  if (t.project_id) t.area_id = null;
  if (t.parent_id) t.parent_key = db.tasks.find((x) => x.id === t.parent_id)?.key ?? null;
  db.tasks.push(t);
  return withCounts(t);
}

function route(method: string, path: string, q: URLSearchParams, body: Record<string, unknown>) {
  const parts = path.split("/").filter(Boolean).slice(1); // drop "api"
  const [head, ref, sub] = parts;
  // /api/agent/* paths are fixed names, not ids.
  const id = head === "agent" ? `/${ref}` : ref ? "/:ref" : "";
  const at = `${method} ${head}${id}${sub ? `/${sub}` : ""}`;
  switch (at) {
    case "GET me":
      return {
        id: "matt",
        workspace_id: "ws",
        name: "Matt",
        email: "matt@example.com",
        via: "dev",
      };
    case "GET settings":
      return { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone };
    case "PATCH settings":
      return body;
    case "GET areas":
      return db.areas;
    case "GET labels":
      return db.labels;
    case "POST labels": {
      const label = { id: lid(++db.seq), name: String(body.name), color: "#64748b" };
      db.labels.push(label);
      return label;
    }
    case "GET projects":
      return projectsWithProgress();
    case "GET projects/:ref":
      return projectsWithProgress().find((p) => p.id === ref);
    case "GET agenda":
      return agenda(q.get("start") ?? undefined, q.get("end") ?? undefined);
    case "POST parse":
      return parse(String(body.text ?? ""));
    case "GET tasks":
      return listTasks(q);
    case "POST tasks":
      return create(body as unknown as Task);
    case "POST tasks/:ref": {
      // POST /api/tasks/quick-add
      const p = parse(String(body.text ?? ""));
      if (body.create_missing && p.unknown_project) {
        const proj = project(++db.seq, p.unknown_project, 0, { area_id: null });
        db.projects.push(proj);
        p.project_id = proj.id;
      }
      for (const name of body.create_missing ? p.unknown_labels : []) {
        const label = { id: lid(++db.seq), name, color: "#64748b" };
        db.labels.push(label);
        p.label_ids.push(label.id);
      }
      return create({
        title: p.title,
        due_date: p.due_date,
        due_time: p.due_time,
        recurrence: p.recurrence,
        priority: (p.priority ?? 0) as Task["priority"],
        status: p.status ?? "todo",
        label_ids: p.label_ids,
        project_id: p.project_id ?? (body.project_id as string | null),
        area_id: p.area_id ?? (body.area_id as string | null),
        parent_id: body.parent_id as string | null,
      });
    }
    case "GET tasks/:ref":
      return withCounts(findTask(ref));
    case "PATCH tasks/:ref": {
      const t = findTask(ref);
      const { clear_recurrence, due_string: _, ...rest } = body;
      return save(t, {
        ...(rest as Partial<Task>),
        ...(clear_recurrence ? { recurrence: null } : {}),
      });
    }
    case "DELETE tasks/:ref":
      db.tasks = db.tasks.filter((t) => t !== findTask(ref));
      return undefined;
    case "POST tasks/:ref/complete": {
      const t = findTask(ref);
      const s = t.recurrence ? (step(t.recurrence) ?? 30) : null;
      const done =
        s !== null && t.due_date
          ? save(t, { due_date: addDays(t.due_date, s), completed_runs: t.completed_runs + 1 })
          : save(t, { status: "done", completed_at: new Date().toISOString() });
      const open = db.tasks.filter((x) => x.parent_id === t.id && !closed(x.status)).length;
      return { task: done, open_subtasks: open };
    }
    case "POST tasks/:ref/reopen":
      return save(findTask(ref), { status: "todo", completed_at: null });
    case "GET tasks/:ref/comments":
      return db.comments.filter((c) => c.task_id === findTask(ref).id);
    case "POST tasks/:ref/comments": {
      const now = new Date().toISOString();
      const c = {
        id: oid(++db.seq),
        task_id: findTask(ref).id,
        body: String(body.body),
        created_at: now,
        updated_at: now,
      };
      db.comments.push(c);
      return c;
    }
    case "GET tasks/:ref/activity":
      return db.activity.filter((a) => a.task_id === findTask(ref).id);
    case "GET agent/settings":
      return {
        enabled: true,
        mode: "suggest",
        instructions: "",
        provider: "anthropic",
        daily_message_cap: 200,
      };
    case "PATCH agent/settings":
      return { enabled: true, mode: "suggest", instructions: "", provider: "anthropic", ...body };
    case "GET agent/conversation":
      return db.conversation;
    case "DELETE agent/conversation":
      db.conversation = [];
      return undefined;
    case "GET pending-changes": {
      const status = q.get("status") ?? "pending";
      return db.pending.filter((p) => status === "all" || p.status === status);
    }
    case "POST pending-changes/:ref/apply":
    case "POST pending-changes/:ref/dismiss": {
      const change = db.pending.find((p) => p.id === ref);
      if (!change) throw new Reply(404, { detail: "Pending change not found" });
      Object.assign(change, {
        status: sub === "apply" ? "applied" : "dismissed",
        resolved_at: new Date().toISOString(),
      });
      return change;
    }
    case "GET api-keys":
      return db.apiKeys;
    case "POST api-keys": {
      const key = {
        id: uuid(6, ++db.seq),
        name: String(body.name),
        kind: (body.kind as ApiKey["kind"]) ?? "rest",
        created_at: new Date().toISOString(),
        last_used_at: null,
        revoked_at: null,
      };
      db.apiKeys.push(key);
      return { ...key, secret: "slate_demo_0123456789abcdef" };
    }
    case "DELETE api-keys/:ref":
      db.apiKeys = db.apiKeys.filter((k) => k.id !== ref);
      return undefined;
    default:
      throw new Reply(404, { detail: `No mock for ${method} ${path}` });
  }
}

function json(status: number, body?: unknown): Response {
  if (body === undefined) return new Response(null, { status: status === 200 ? 204 : status });
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Answer /api requests from the in-memory data and pass everything else through. */
export function installMockApi() {
  const real = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
    if (!url.pathname.startsWith("/api/")) return real(input, init);
    const method = (init?.method ?? "GET").toUpperCase();
    if (scenario === "error") return json(503, { detail: "Service unavailable" });
    if (scenario === "loading" && url.pathname !== "/api/me") return new Promise(() => {});
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    // A short delay, like a fast network, so loading states flash as they do in the app.
    await new Promise((r) => setTimeout(r, 60));
    try {
      return json(200, clone(route(method, url.pathname, url.searchParams, body)));
    } catch (err) {
      if (err instanceof Reply) return json(err.status, err.body);
      throw err;
    }
  };
}
