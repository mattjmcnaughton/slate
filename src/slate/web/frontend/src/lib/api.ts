// Typed client for the Slate HTTP API. Types mirror src/slate/dtos/__init__.py.
// Dates are local ISO dates ("2026-11-21"), times are "HH:MM:SS", timestamps are UTC ISO.

const API_BASE = import.meta.env.VITE_API_URL ?? "";

export type TaskStatus = "backlog" | "todo" | "in_progress" | "done" | "canceled";
export type ProjectStatus = "planned" | "active" | "paused" | "done" | "canceled";
export type Priority = 0 | 1 | 2 | 3 | 4;

export interface User {
  id: string;
  name: string;
  email: string | null;
  via: string;
}

export interface Settings {
  timezone: string;
}

export interface Recurrence {
  rrule: string;
  mode: "fixed" | "after_completion";
  dtstart: string;
  time: string | null;
  text: string;
}

export interface Area {
  id: number;
  uuid: string;
  name: string;
  color: string;
  position: number;
}

export interface AreaIn {
  name: string;
  color?: string;
  position?: number;
}

export interface Project {
  id: number;
  uuid: string;
  name: string;
  area_id: number | null;
  status: ProjectStatus;
  description: string;
  target_date: string | null;
  color: string | null;
  position: number;
  progress_done: number;
  progress_total: number;
  open_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectIn {
  name: string;
  area_id?: number | null;
  status?: ProjectStatus;
  description?: string;
  target_date?: string | null;
  color?: string | null;
  position?: number;
}

export type ProjectPatch = Partial<ProjectIn>;

export interface Label {
  id: number;
  uuid: string;
  name: string;
  color: string;
}

export interface Task {
  id: number;
  uuid: string;
  key: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  project_id: number | null;
  area_id: number | null;
  parent_id: number | null;
  label_ids: number[];
  due_date: string | null;
  due_time: string | null;
  recurrence: Recurrence | null;
  completed_runs: number;
  completed_at: string | null;
  comment_count: number;
  subtask_count: number;
  open_subtask_count: number;
  source: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskIn {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: Priority;
  project_id?: number | null;
  area_id?: number | null;
  parent_id?: number | null;
  label_ids?: number[];
  due_date?: string | null;
  due_time?: string | null;
  due_string?: string | null;
}

/** Leave a field out to keep it; send null to clear it. */
export interface TaskPatch {
  title?: string;
  description?: string;
  status?: TaskStatus;
  priority?: Priority;
  project_id?: number | null;
  area_id?: number | null;
  parent_id?: number | null;
  label_ids?: number[];
  due_date?: string | null;
  due_time?: string | null;
  due_string?: string;
  clear_recurrence?: boolean;
}

export interface CompleteResult {
  task: Task;
  open_subtasks: number;
}

export interface Comment {
  id: number;
  uuid: string;
  task_id: number;
  body: string;
  created_at: string;
  updated_at: string;
}

export type ActivityKind =
  | "created"
  | "updated"
  | "status"
  | "completed_run"
  | "completed"
  | "reopened"
  | "commented"
  | "imported";

export interface Activity {
  id: number;
  task_id: number;
  kind: ActivityKind | string;
  data: Record<string, unknown>;
  created_at: string;
}

export type TokenKind = "date" | "recurrence" | "project" | "label" | "priority" | "status";

export interface Token {
  kind: TokenKind | string;
  start: number;
  end: number;
  text: string;
  unresolved: boolean;
}

export interface ParseResult {
  title: string;
  due_date: string | null;
  due_time: string | null;
  recurrence: Recurrence | null;
  area_id: number | null;
  project_id: number | null;
  unknown_project: string | null;
  label_ids: number[];
  unknown_labels: string[];
  priority: number | null;
  status: TaskStatus | null;
  tokens: Token[];
}

export interface QuickAddIn {
  text: string;
  create_missing?: boolean;
  project_id?: number | null;
  area_id?: number | null;
  parent_id?: number | null;
}

export interface Ghost {
  task_id: number;
  date: string;
}

export interface AgendaDay {
  date: string;
  tasks: Task[];
  ghosts: Ghost[];
}

export interface Agenda {
  today: string;
  overdue: Task[];
  days: AgendaDay[];
}

export type TaskSort = "due" | "priority" | "created" | "updated" | "position";

export interface TaskQuery {
  project_id?: number;
  area_id?: number;
  inbox?: boolean;
  /** 0 selects top-level tasks only. */
  parent_id?: number;
  status?: TaskStatus[];
  priority?: number[];
  label_id?: number;
  due_before?: string;
  due_after?: string;
  has_due?: boolean;
  recurring?: boolean;
  q?: string;
  include_closed?: boolean;
  sort?: TaskSort;
  order?: "asc" | "desc";
  limit?: number;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type QueryValue = string | number | boolean | undefined | null | (string | number)[];

export function queryString(params: Record<string, QueryValue>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) q.append(key, String(v));
    } else {
      q.append(key, String(value));
    }
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
      .join("; ");
  }
  return fallback;
}

export function signInUrl(): string {
  const here = `${window.location.pathname}${window.location.search}`;
  return `/auth/signin?return_to=${encodeURIComponent(here)}`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    window.location.assign(signInUrl());
    throw new ApiError(401, "Signed out");
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      message = detailMessage((await res.json()).detail, message);
    } catch {
      // Not JSON; keep the status line.
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});
const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
const del = (path: string) => request<void>("DELETE", path);

const ref = (r: number | string) => encodeURIComponent(String(r));

export const api = {
  me: () => get<User>("/api/me"),
  settings: () => get<Settings>("/api/settings"),
  patchSettings: (body: Settings) => patch<Settings>("/api/settings", body),

  areas: () => get<Area[]>("/api/areas"),
  createArea: (body: AreaIn) => post<Area>("/api/areas", body),
  patchArea: (id: number, body: Partial<AreaIn>) => patch<Area>(`/api/areas/${id}`, body),
  deleteArea: (id: number) => del(`/api/areas/${id}`),

  projects: (areaId?: number) => get<Project[]>(`/api/projects${queryString({ area_id: areaId })}`),
  project: (id: number) => get<Project>(`/api/projects/${id}`),
  createProject: (body: ProjectIn) => post<Project>("/api/projects", body),
  patchProject: (id: number, body: ProjectPatch) => patch<Project>(`/api/projects/${id}`, body),
  deleteProject: (id: number) => del(`/api/projects/${id}`),

  labels: () => get<Label[]>("/api/labels"),
  createLabel: (body: { name: string; color?: string }) => post<Label>("/api/labels", body),
  deleteLabel: (id: number) => del(`/api/labels/${id}`),

  tasks: (query: TaskQuery = {}) =>
    get<Task[]>(`/api/tasks${queryString(query as Record<string, QueryValue>)}`),
  task: (r: number | string) => get<Task>(`/api/tasks/${ref(r)}`),
  createTask: (body: TaskIn) => post<Task>("/api/tasks", body),
  quickAdd: (body: QuickAddIn) => post<Task>("/api/tasks/quick-add", body),
  patchTask: (r: number | string, body: TaskPatch) => patch<Task>(`/api/tasks/${ref(r)}`, body),
  deleteTask: (r: number | string) => del(`/api/tasks/${ref(r)}`),
  complete: (r: number | string) => post<CompleteResult>(`/api/tasks/${ref(r)}/complete`),
  reopen: (r: number | string) => post<Task>(`/api/tasks/${ref(r)}/reopen`),

  comments: (r: number | string) => get<Comment[]>(`/api/tasks/${ref(r)}/comments`),
  addComment: (r: number | string, body: string) =>
    post<Comment>(`/api/tasks/${ref(r)}/comments`, { body }),
  patchComment: (id: number, body: string) => patch<Comment>(`/api/comments/${id}`, { body }),
  deleteComment: (id: number) => del(`/api/comments/${id}`),
  activity: (r: number | string) => get<Activity[]>(`/api/tasks/${ref(r)}/activity`),

  agenda: (start?: string, end?: string) =>
    get<Agenda>(`/api/agenda${queryString({ start, end })}`),
  parse: (text: string) => post<ParseResult>("/api/parse", { text }),
};
