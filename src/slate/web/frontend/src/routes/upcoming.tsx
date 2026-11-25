import { createFileRoute } from "@tanstack/react-router";
import { QuickAdd } from "../components/QuickAdd";
import { type Group, PageHeader, TaskGroups, usePageContext } from "../components/TaskList";
import { IconRepeat } from "../components/icons";
import type { Agenda, Ghost, Task } from "../lib/api";
import { diffDays, formatShort, monthName, weekdayName } from "../lib/dates";
import { useAgenda } from "../lib/queries";
import { useUI } from "../stores/ui";

export const Route = createFileRoute("/upcoming")({
  component: Upcoming,
});

const DAYS = 21;

function dayTitle(date: string, today: string) {
  const delta = diffDays(date, today);
  const name = delta === 0 ? "Today" : delta === 1 ? "Tomorrow" : weekdayName(date);
  return (
    <>
      {name}
      <span className="font-normal text-ink3">
        {monthName(date, true)} {Number(date.slice(8))}
      </span>
    </>
  );
}

function GhostRow({ ghost, task }: { ghost: Ghost; task: Task | undefined }) {
  return (
    <button
      type="button"
      onClick={() => useUI.getState().openDetail(ghost.task_id)}
      title="A later run of a repeating task. Opens the task."
      className="flex min-h-[40px] w-full items-center gap-2.5 border-b border-dashed border-line px-4 text-left opacity-55 hover:opacity-80 desk:min-h-[34px] desk:px-5"
    >
      <span className="hidden w-[52px] shrink-0 text-[12px] tabular-nums text-ink3 desk:block">
        {task?.key}
      </span>
      <span className="hidden w-[14px] desk:block" />
      <span className="h-[14px] w-[14px] shrink-0 rounded-full border border-dashed border-ink3" />
      <span className="min-w-0 flex-1 truncate text-[14px] italic text-ink2 desk:text-[13.5px]">
        {task?.title ?? "Repeating task"}
      </span>
      <span className="inline-flex items-center gap-1 text-[12px] text-ink3">
        <IconRepeat size={12} />
        {task?.recurrence?.text ?? "repeats"}
      </span>
    </button>
  );
}

function allTasks(a: Agenda): Map<string, Task> {
  const map = new Map<string, Task>();
  for (const t of a.overdue) map.set(t.id, t);
  for (const d of a.days) for (const t of d.tasks) map.set(t.id, t);
  return map;
}

function Upcoming() {
  const { data } = useAgenda(DAYS);
  usePageContext({}, []);
  if (!data) return null;
  const byId = allTasks(data);
  const last = data.days[data.days.length - 1]?.date;

  const groups: Group[] = [
    { key: "overdue", title: "Overdue", tasks: data.overdue, tone: "red" },
    ...data.days.map((d) => ({
      key: d.date,
      title: dayTitle(d.date, data.today),
      tasks: d.tasks,
      hideDue: true,
      extra: d.ghosts.length ? (
        <>
          {d.ghosts.map((g) => (
            <GhostRow key={`${g.task_id}-${g.date}`} ghost={g} task={byId.get(g.task_id)} />
          ))}
        </>
      ) : undefined,
    })),
  ];

  return (
    <div className="mx-auto max-w-[920px]">
      <PageHeader
        serif
        title="Upcoming"
        sub={last ? `${formatShort(data.today)} to ${formatShort(last, data.today)}` : undefined}
      >
        <div className="-mx-1 mt-4 desk:-mx-2">
          <QuickAdd variant="inline" placeholder="Add a task: Book flights fri #home" />
        </div>
      </PageHeader>
      <TaskGroups groups={groups} />
    </div>
  );
}
