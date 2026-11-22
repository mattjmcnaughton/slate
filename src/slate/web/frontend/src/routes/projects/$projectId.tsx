import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Board } from "../../components/Board";
import { QuickAdd } from "../../components/QuickAdd";
import {
  Empty,
  type Group,
  PageHeader,
  TaskGroups,
  usePageContext,
} from "../../components/TaskList";
import { ProgressBar } from "../../components/TaskMeta";
import { Dot, IconBoard, IconList, IconRepeat, STATUSES } from "../../components/icons";
import { diffDays, formatShort } from "../../lib/dates";
import { useLookups, useTasks, useToday } from "../../lib/queries";

type View = "list" | "board";

export const Route = createFileRoute("/projects/$projectId")({
  validateSearch: (s: Record<string, unknown>): { view?: View } =>
    s.view === "board" ? { view: "board" } : {},
  component: ProjectPage,
});

const PROJECT_STATUS: Record<string, string> = {
  planned: "Planned",
  active: "Active",
  paused: "Paused",
  done: "Done",
  canceled: "Canceled",
};

function ProjectPage() {
  const { projectId } = Route.useParams();
  const { view = "list" } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const id = Number(projectId);
  const lookups = useLookups();
  const today = useToday();
  const project = lookups.projects.get(id);
  const area = project?.area_id ? lookups.areas.get(project.area_id) : undefined;
  const { data: tasks } = useTasks({
    project_id: id,
    parent_id: 0,
    include_closed: true,
    sort: "due",
  });

  const setView = (v: View) =>
    navigate({ search: v === "board" ? { view: "board" } : {}, replace: true });
  usePageContext(
    { projectId: id, areaId: null, toggleView: () => setView(view === "board" ? "list" : "board") },
    [id, view],
  );

  if (!project) {
    return lookups.projects.size ? <Empty title="This project does not exist" /> : null;
  }

  const target = project.target_date;
  const days = target && today ? diffDays(target, today) : null;
  const sub = (
    <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {area && (
        <span className="inline-flex items-center gap-1.5">
          <Dot color={area.color} size={7} />
          {area.name}
        </span>
      )}
      <span>{PROJECT_STATUS[project.status]}</span>
      {target && (
        <span className={days !== null && days < 0 ? "text-red" : ""}>
          Target {formatShort(target, today)}
          {days !== null &&
            (days < 0 ? `, ${-days}d late` : days === 0 ? ", today" : `, in ${days}d`)}
        </span>
      )}
      <ProgressBar done={project.progress_done} total={project.progress_total} />
    </span>
  );

  const toggle = (
    <div
      className="hidden rounded-md border border-line p-0.5 desk:flex"
      role="group"
      aria-label="View"
    >
      {(["list", "board"] as const).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={view === v}
          onClick={() => setView(v)}
          title={`${v === "list" ? "List" : "Board"} (V)`}
          className={`flex h-7 items-center gap-1.5 rounded px-2 text-[12.5px] ${
            view === v ? "bg-hover text-ink" : "text-ink3 hover:text-ink"
          }`}
        >
          {v === "list" ? <IconList size={14} /> : <IconBoard size={14} />}
          {v === "list" ? "List" : "Board"}
        </button>
      ))}
    </div>
  );

  const open = (tasks ?? []).filter((t) => t.status !== "done" && t.status !== "canceled");
  const closed = (tasks ?? []).filter((t) => t.status === "done" || t.status === "canceled");
  const groups: Group[] = [
    ...STATUSES.filter((s) => s.value !== "done" && s.value !== "canceled").map((s) => ({
      key: s.value,
      title: s.label,
      tasks: open.filter((t) => t.status === s.value && !t.recurrence),
    })),
    {
      key: "recurring",
      title: (
        <span className="inline-flex items-center gap-1.5">
          <IconRepeat size={13} className="text-teal" />
          Recurring
        </span>
      ),
      tasks: open.filter((t) => t.recurrence),
    },
    { key: "closed", title: "Done and canceled", tasks: closed },
  ];

  return (
    <div className={view === "board" ? "" : "mx-auto max-w-[920px]"}>
      <PageHeader title={project.name} sub={sub} actions={toggle}>
        {project.description && (
          <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-ink2">
            {project.description}
          </p>
        )}
        <div className={`-mx-1 mt-4 desk:-mx-2 ${view === "board" ? "max-w-[620px]" : ""}`}>
          <QuickAdd variant="inline" placeholder={`Add to ${project.name}: Call Sam fri p2`} />
        </div>
      </PageHeader>
      {tasks &&
        (view === "board" ? (
          <Board tasks={tasks} />
        ) : (
          <TaskGroups
            groups={groups}
            hideWhere
            empty={<Empty title="No tasks yet" body="Add the first one above." />}
          />
        ))}
    </div>
  );
}
