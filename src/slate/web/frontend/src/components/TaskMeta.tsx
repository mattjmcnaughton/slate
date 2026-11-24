import type { Task } from "../lib/api";
import { dueTone, formatDue, formatTime } from "../lib/dates";
import type { Lookups } from "../lib/queries";
import { Dot, IconComment, IconRepeat, IconSubtasks } from "./icons";

const TONE: Record<string, string> = {
  overdue: "text-red",
  today: "text-accent",
  soon: "text-ink2",
  later: "text-ink3",
};

export function DueChip({ task, today }: { task: Task; today?: string }) {
  if (!task.due_date || !today) return null;
  const closed = task.status === "done" || task.status === "canceled";
  const tone = closed ? "text-ink3" : TONE[dueTone(task.due_date, today)];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap text-[12px] ${tone}`}>
      {task.recurrence && <IconRepeat size={12} />}
      {formatDue(task.due_date, today)}
      {task.due_time && <span className="text-ink3">{formatTime(task.due_time)}</span>}
    </span>
  );
}

export function LabelChips({
  ids,
  lookups,
  max = 3,
}: { ids: string[]; lookups: Lookups; max?: number }) {
  if (!ids.length) return null;
  const labels = ids.map((id) => lookups.labels.get(id)).filter((l) => l !== undefined);
  return (
    <span className="flex items-center gap-1">
      {labels.slice(0, max).map((l) => (
        <span key={l.id} className="chip">
          <Dot color={l.color} size={6} />
          {l.name}
        </span>
      ))}
      {labels.length > max && <span className="text-[11px] text-ink3">+{labels.length - max}</span>}
    </span>
  );
}

/** Project (or area) the task is filed under, with its color dot. */
export function Where({ task, lookups }: { task: Task; lookups: Lookups }) {
  const project = task.project_id ? lookups.projects.get(task.project_id) : undefined;
  const area = project?.area_id
    ? lookups.areas.get(project.area_id)
    : task.area_id
      ? lookups.areas.get(task.area_id)
      : undefined;
  const name = project?.name ?? area?.name;
  if (!name) return null;
  return (
    <span className="inline-flex max-w-[11rem] items-center gap-1.5 truncate text-[12px] text-ink3">
      <Dot color={project?.color ?? area?.color ?? "rgb(var(--ink3))"} size={7} />
      <span className="truncate">{name}</span>
    </span>
  );
}

export function Counts({ task }: { task: Task }) {
  return (
    <>
      {task.subtask_count > 0 && (
        <span className="inline-flex items-center gap-1 text-[12px] text-ink3">
          <IconSubtasks size={12} />
          {task.subtask_count - task.open_subtask_count}/{task.subtask_count}
        </span>
      )}
      {task.comment_count > 0 && (
        <span className="inline-flex items-center gap-1 text-[12px] text-ink3">
          <IconComment size={12} />
          {task.comment_count}
        </span>
      )}
    </>
  );
}

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative h-1.5 w-24 overflow-hidden rounded-full bg-line">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="tabular-nums">
        {done}/{total}
      </span>
    </span>
  );
}
