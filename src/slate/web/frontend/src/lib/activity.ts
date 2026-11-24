import type { Activity, TaskStatus } from "./api";
import { formatShort, formatTime } from "./dates";
import type { Lookups } from "./queries";

const STATUS: Record<string, string> = {
  backlog: "Backlog",
  todo: "Todo",
  in_progress: "In progress",
  done: "Done",
  canceled: "Canceled",
};
const PRIORITY = ["no priority", "Urgent", "High", "Medium", "Low"];

const str = (v: unknown) => (v === null || v === undefined || v === "" ? null : String(v));

function value(field: string, v: unknown, lookups: Lookups): string | null {
  const s = str(v);
  if (s === null) return null;
  switch (field) {
    case "status":
      return STATUS[s] ?? s;
    case "priority":
      return PRIORITY[Number(s)] ?? s;
    case "project_id":
      return lookups.projects.get(s)?.name ?? `project ${s}`;
    case "area_id":
      return lookups.areas.get(s)?.name ?? `area ${s}`;
    case "parent_id":
      return "another task";
    case "due_date":
      return formatShort(s);
    case "due_time":
      return formatTime(s);
    case "label_ids":
      return Array.isArray(v)
        ? v.map((id) => lookups.labels.get(String(id))?.name ?? `#${id}`).join(", ") || null
        : s;
    default:
      return s;
  }
}

const FIELD: Record<string, string> = {
  title: "the title",
  description: "the description",
  status: "status",
  priority: "priority",
  project_id: "project",
  area_id: "area",
  parent_id: "parent",
  due_date: "due date",
  due_time: "due time",
  recurrence: "repeat",
  label_ids: "labels",
};

/** One line describing an activity entry, such as "Moved from Todo to In progress". */
export function describeActivity(a: Activity, lookups: Lookups): string {
  const d = a.data;
  switch (a.kind) {
    case "created":
      return "Created the task";
    case "imported":
      return `Imported${d.source ? ` from ${String(d.source)}` : ""}`;
    case "completed":
      return "Completed";
    case "reopened":
      return "Reopened";
    case "completed_run": {
      const next = str(d.next);
      return next ? `Completed a run; next is ${formatShort(next)}` : "Completed the last run";
    }
    case "commented":
      return "Commented";
    case "status":
    case "updated": {
      const field = String(d.field ?? "");
      if (field === "title") return `Renamed to “${str(d.to) ?? ""}”`;
      if (field === "description") return "Edited the description";
      const from = value(field, d.from, lookups);
      const to = value(field, d.to, lookups);
      const name = FIELD[field] ?? field;
      if (field === "status" && from && to) return `Moved from ${from} to ${to}`;
      if (to === null) return `Cleared ${name}${from ? ` (was ${from})` : ""}`;
      if (from === null) return `Set ${name} to ${to}`;
      return `Changed ${name} from ${from} to ${to}`;
    }
    default:
      return a.kind;
  }
}

export function isClosed(s: TaskStatus) {
  return s === "done" || s === "canceled";
}
