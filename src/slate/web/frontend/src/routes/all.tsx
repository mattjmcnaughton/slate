import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Empty, PageHeader, usePageContext } from "../components/TaskList";
import { DueChip, LabelChips, Where } from "../components/TaskMeta";
import { useVisibleIds } from "../components/TaskRow";
import { TaskRow } from "../components/TaskRow";
import { PRIORITIES, PriorityIcon, STATUSES, StatusIcon, statusLabel } from "../components/icons";
import { useIsPhone } from "../hooks/useMedia";
import type { Task, TaskQuery, TaskSort, TaskStatus } from "../lib/api";
import { addDays, formatRelative } from "../lib/dates";
import {
  useAreas,
  useLabels,
  useLookups,
  useProjects,
  useTasks,
  useToday,
  useToggleComplete,
} from "../lib/queries";
import { useUI } from "../stores/ui";

type DuePreset = "overdue" | "today" | "week" | "month" | "none" | "custom";

interface Search {
  q?: string;
  area?: string;
  project?: string;
  status?: TaskStatus[];
  priority?: number;
  label?: string;
  due?: DuePreset;
  from?: string;
  to?: string;
  sort?: Exclude<TaskSort, "position">;
  order?: "asc" | "desc";
}

const STATUS_VALUES = STATUSES.map((s) => s.value);
const num = (v: unknown) =>
  v === undefined || v === "" || Number.isNaN(Number(v)) ? undefined : Number(v);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const uuid = (v: unknown) => (typeof v === "string" && UUID_RE.test(v) ? v : undefined);
const isoDate = (v: unknown) =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : undefined;

export const Route = createFileRoute("/all")({
  validateSearch: (s: Record<string, unknown>): Search => {
    const rawStatus = Array.isArray(s.status)
      ? s.status
      : typeof s.status === "string"
        ? s.status.split(",")
        : [];
    const status = rawStatus.filter((x): x is TaskStatus =>
      STATUS_VALUES.includes(x as TaskStatus),
    );
    const due = ["overdue", "today", "week", "month", "none", "custom"].includes(String(s.due))
      ? (s.due as DuePreset)
      : undefined;
    return {
      q: typeof s.q === "string" && s.q ? s.q : undefined,
      area: uuid(s.area),
      project: uuid(s.project),
      status: status.length ? status : undefined,
      priority: num(s.priority),
      label: uuid(s.label),
      due,
      from: due === "custom" ? isoDate(s.from) : undefined,
      to: due === "custom" ? isoDate(s.to) : undefined,
      sort: ["due", "priority", "created", "updated"].includes(String(s.sort))
        ? (s.sort as Search["sort"])
        : undefined,
      order: s.order === "desc" ? "desc" : undefined,
    };
  },
  component: AllTasks,
});

function toQuery(s: Search, today: string | undefined): TaskQuery {
  const q: TaskQuery = {
    q: s.q,
    area_id: s.area,
    project_id: s.project,
    status: s.status,
    priority: s.priority === undefined ? undefined : [s.priority],
    label_id: s.label,
    sort: s.sort ?? "due",
    order: s.order ?? "asc",
    // Asking for done or canceled by status already includes them.
    include_closed: false,
  };
  if (today) {
    switch (s.due) {
      case "overdue":
        q.due_before = addDays(today, -1);
        break;
      case "today":
        q.due_after = today;
        q.due_before = today;
        break;
      case "week":
        q.due_after = today;
        q.due_before = addDays(today, 6);
        break;
      case "month":
        q.due_after = today;
        q.due_before = addDays(today, 29);
        break;
      case "none":
        q.has_due = false;
        break;
      case "custom":
        q.due_after = s.from;
        q.due_before = s.to;
        break;
    }
  }
  return q;
}

const selectCls =
  "h-7 rounded-md border border-line bg-panel px-2 text-[12.5px] text-ink2 outline-none hover:border-line2 focus:border-accent";
const activeCls = "!border-accent/60 !text-ink";

function AllTasks() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const today = useToday();
  const areas = useAreas().data ?? [];
  const projects = useProjects().data ?? [];
  const labels = useLabels().data ?? [];
  const phone = useIsPhone();
  const set = (patch: Partial<Search>) =>
    navigate({ search: (prev: Search) => ({ ...prev, ...patch }), replace: true });
  const { data, isFetching } = useTasks(toQuery(search, today), Boolean(today));
  usePageContext(
    { projectId: search.project ?? null, areaId: search.project ? null : (search.area ?? null) },
    [search.project, search.area],
  );

  const [q, setQ] = useState(search.q ?? "");
  useEffect(() => setQ(search.q ?? ""), [search.q]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      if ((search.q ?? "") !== q) set({ q: q || undefined });
    }, 250);
    return () => window.clearTimeout(t);
  });

  const filtered = Object.entries(search).some(
    ([k, v]) => v !== undefined && k !== "sort" && k !== "order",
  );
  const toggleStatus = (s: TaskStatus) => {
    const cur = search.status ?? [];
    const next = cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s];
    set({ status: next.length ? next : undefined });
  };
  const areaProjects = search.area ? projects.filter((p) => p.area_id === search.area) : projects;

  return (
    <div className="pb-10">
      <PageHeader
        title="All tasks"
        sub={
          data ? `${data.length} task${data.length === 1 ? "" : "s"}${isFetching ? "…" : ""}` : " "
        }
      />
      <div className="mt-4 flex flex-wrap items-center gap-1.5 border-b border-line px-4 pb-3 desk:px-5">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search titles"
          aria-label="Search titles"
          className={`${selectCls} w-full desk:w-48 ${search.q ? activeCls : ""}`}
        />
        <select
          aria-label="Area"
          value={search.area ?? ""}
          onChange={(e) => set({ area: uuid(e.target.value), project: undefined })}
          className={`${selectCls} ${search.area ? activeCls : ""}`}
        >
          <option value="">Any area</option>
          {areas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Project"
          value={search.project ?? ""}
          onChange={(e) => set({ project: uuid(e.target.value) })}
          className={`${selectCls} ${search.project ? activeCls : ""}`}
        >
          <option value="">Any project</option>
          {areaProjects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <div
          className="flex items-center rounded-md border border-line bg-panel p-0.5"
          role="group"
          aria-label="Status"
        >
          {STATUSES.map((s) => {
            const on = search.status?.includes(s.value);
            return (
              <button
                key={s.value}
                type="button"
                aria-pressed={on}
                title={s.label}
                onClick={() => toggleStatus(s.value)}
                className={`flex h-6 items-center gap-1 rounded px-1.5 text-[12px] ${
                  on ? "bg-accent-soft text-ink" : "text-ink3 hover:text-ink"
                }`}
              >
                <StatusIcon status={s.value} size={12} />
                <span className="hidden lg:inline">{s.label}</span>
              </button>
            );
          })}
        </div>
        <select
          aria-label="Priority"
          value={search.priority ?? ""}
          onChange={(e) => set({ priority: num(e.target.value) })}
          className={`${selectCls} ${search.priority !== undefined ? activeCls : ""}`}
        >
          <option value="">Any priority</option>
          {[1, 2, 3, 4, 0].map((p) => (
            <option key={p} value={p}>
              {PRIORITIES[p].label}
            </option>
          ))}
        </select>
        <select
          aria-label="Label"
          value={search.label ?? ""}
          onChange={(e) => set({ label: uuid(e.target.value) })}
          className={`${selectCls} ${search.label ? activeCls : ""}`}
        >
          <option value="">Any label</option>
          {labels.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Due"
          value={search.due ?? ""}
          onChange={(e) =>
            set({
              due: (e.target.value || undefined) as DuePreset | undefined,
              from: undefined,
              to: undefined,
            })
          }
          className={`${selectCls} ${search.due ? activeCls : ""}`}
        >
          <option value="">Any due date</option>
          <option value="overdue">Overdue</option>
          <option value="today">Due today</option>
          <option value="week">Next 7 days</option>
          <option value="month">Next 30 days</option>
          <option value="none">No due date</option>
          <option value="custom">Custom range</option>
        </select>
        {search.due === "custom" && (
          <>
            <input
              type="date"
              aria-label="Due from"
              value={search.from ?? ""}
              onChange={(e) => set({ from: e.target.value || undefined })}
              className={selectCls}
            />
            <span className="text-[12px] text-ink3">to</span>
            <input
              type="date"
              aria-label="Due to"
              value={search.to ?? ""}
              onChange={(e) => set({ to: e.target.value || undefined })}
              className={selectCls}
            />
          </>
        )}
        <span className="flex-1" />
        <select
          aria-label="Sort"
          value={search.sort ?? "due"}
          onChange={(e) =>
            set({ sort: e.target.value === "due" ? undefined : (e.target.value as Search["sort"]) })
          }
          className={selectCls}
        >
          <option value="due">Sort by due</option>
          <option value="priority">Sort by priority</option>
          <option value="created">Sort by created</option>
          <option value="updated">Sort by updated</option>
        </select>
        <button
          type="button"
          onClick={() => set({ order: search.order === "desc" ? undefined : "desc" })}
          className={selectCls}
          aria-label={search.order === "desc" ? "Descending" : "Ascending"}
          title={search.order === "desc" ? "Descending" : "Ascending"}
        >
          {search.order === "desc" ? "↓ Desc" : "↑ Asc"}
        </button>
        {filtered && (
          <button
            type="button"
            onClick={() => navigate({ search: {}, replace: true })}
            className="h-7 px-1.5 text-[12.5px] text-ink3 hover:text-ink"
          >
            Clear filters
          </button>
        )}
      </div>
      {data &&
        (data.length === 0 ? (
          <Empty title="No tasks match these filters" body="Loosen a filter or clear them all." />
        ) : phone ? (
          <PhoneList tasks={data} />
        ) : (
          <Table tasks={data} />
        ))}
    </div>
  );
}

function PhoneList({ tasks }: { tasks: Task[] }) {
  const lookups = useLookups();
  const today = useToday();
  useVisibleIds(tasks.map((t) => t.id));
  return (
    <div>
      {tasks.map((t) => (
        <TaskRow key={t.id} task={t} today={today} lookups={lookups} />
      ))}
    </div>
  );
}

function Table({ tasks }: { tasks: Task[] }) {
  const lookups = useLookups();
  const today = useToday();
  const toggle = useToggleComplete();
  const selectedId = useUI((s) => s.selectedId);
  const detailId = useUI((s) => s.detailId);
  const checked = useUI((s) => s.checkedIds);
  useVisibleIds(tasks.map((t) => t.id));

  const th = "h-8 px-2 text-left text-[12px] font-medium text-ink3";
  return (
    <table className="w-full table-fixed border-collapse text-[13px]">
      <colgroup>
        <col className="w-[76px]" />
        <col />
        <col className="w-[120px]" />
        <col className="w-[44px]" />
        <col className="w-[170px]" />
        <col className="w-[150px] max-xl:w-0" />
        <col className="w-[110px]" />
        <col className="w-[80px] max-lg:w-0" />
      </colgroup>
      <thead className="sticky top-0 z-10 bg-bg">
        <tr className="border-b border-line">
          <th className={`${th} pl-5`}>ID</th>
          <th className={th}>Title</th>
          <th className={th}>Status</th>
          <th className={th} title="Priority">
            Pri
          </th>
          <th className={th}>Project</th>
          <th className={`${th} max-xl:hidden`}>Labels</th>
          <th className={th}>Due</th>
          <th className={`${th} max-lg:hidden`}>Updated</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((t) => {
          const on = detailId === t.id || checked.includes(t.id);
          const closed = t.status === "done" || t.status === "canceled";
          return (
            <tr
              key={t.id}
              data-task-id={t.id}
              ref={(el) => {
                if (el && selectedId === t.id) el.scrollIntoView({ block: "nearest" });
              }}
              onMouseMove={() => selectedId !== t.id && useUI.getState().select(t.id)}
              onKeyDown={() => {}}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey) useUI.getState().toggleChecked(t.id);
                else useUI.getState().openDetail(t.id);
              }}
              className={`h-9 cursor-default border-b border-line/70 ${
                on ? "row-open" : selectedId === t.id ? "bg-hover" : "bg-panel"
              }`}
            >
              <td className="relative pl-5 pr-2 text-[12px] tabular-nums text-ink3">
                {(selectedId === t.id || checked.includes(t.id)) && (
                  <span className="absolute inset-y-0 left-0 w-[2px] bg-accent" />
                )}
                {t.key}
              </td>
              <td className="px-2">
                <div className="flex min-w-0 items-center gap-2">
                  {t.parent_id && <span className="text-[11.5px] text-ink3">{t.parent_key} ›</span>}
                  <span className={`truncate ${closed ? "text-ink3 line-through" : ""}`}>
                    {t.title}
                  </span>
                </div>
              </td>
              <td className="px-2">
                <button
                  type="button"
                  className="flex items-center gap-1.5 text-[12.5px] text-ink2"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(t.id);
                  }}
                  title={closed ? "Reopen" : "Complete"}
                >
                  <StatusIcon status={t.status} />
                  {statusLabel(t.status)}
                </button>
              </td>
              <td className="px-2">
                <PriorityIcon priority={t.priority} />
              </td>
              <td className="px-2">
                <Where task={t} lookups={lookups} />
              </td>
              <td className="overflow-hidden px-2 max-xl:hidden">
                <LabelChips ids={t.label_ids} lookups={lookups} max={2} />
              </td>
              <td className="px-2">
                <DueChip task={t} today={today} />
              </td>
              <td className="px-2 text-[12px] text-ink3 max-lg:hidden">
                {formatRelative(t.updated_at)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
