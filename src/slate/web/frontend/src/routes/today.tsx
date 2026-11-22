import { createFileRoute } from "@tanstack/react-router";
import { QuickAdd } from "../components/QuickAdd";
import { Empty, PageHeader, TaskGroups, usePageContext } from "../components/TaskList";
import { formatLong } from "../lib/dates";
import { useAgenda } from "../lib/queries";

export const Route = createFileRoute("/today")({
  component: Today,
});

function Today() {
  const { data } = useAgenda();
  usePageContext({ dueToday: true }, []);
  if (!data) return null;

  const todayTasks = data.days.find((d) => d.date === data.today)?.tasks ?? [];
  const open = todayTasks.filter((t) => t.status !== "done" && t.status !== "canceled");
  const done = todayTasks.filter((t) => t.status === "done");
  const overdue = data.overdue;
  const parts = [
    open.length ? `${open.length} to do` : "Nothing left to do",
    overdue.length ? `${overdue.length} overdue` : null,
    done.length ? `${done.length} done` : null,
  ].filter(Boolean);

  return (
    <div className="mx-auto max-w-[920px]">
      <PageHeader serif title={formatLong(data.today)} sub={parts.join(", ")}>
        <div className="-mx-1 mt-4 desk:-mx-2">
          <QuickAdd variant="inline" />
        </div>
      </PageHeader>
      <TaskGroups
        groups={[
          { key: "overdue", title: "Overdue", tasks: overdue, tone: "red" },
          { key: "today", title: overdue.length ? "Today" : undefined, tasks: open, hideDue: true },
          { key: "done", title: "Done today", tasks: done, hideDue: true },
        ]}
        empty={
          <Empty
            title="All clear for today"
            body="Press C to add a task, or plan ahead in Upcoming."
          />
        }
      />
    </div>
  );
}
