import { Link, createFileRoute } from "@tanstack/react-router";
import { PageHeader, usePageContext } from "../../components/TaskList";
import { ProgressBar } from "../../components/TaskMeta";
import { Dot } from "../../components/icons";
import type { Project } from "../../lib/api";
import { formatShort } from "../../lib/dates";
import { useAreas, useProjects, useToday } from "../../lib/queries";

export const Route = createFileRoute("/projects/")({
  component: Projects,
});

const STATUS: Record<string, string> = {
  planned: "Planned",
  active: "Active",
  paused: "Paused",
  done: "Done",
  canceled: "Canceled",
};

function ProjectLine({ p, today }: { p: Project; today?: string }) {
  return (
    <Link
      to="/projects/$projectId"
      params={{ projectId: p.id }}
      className="flex min-h-[44px] items-center gap-3 border-b border-line/70 bg-panel px-4 text-[14px] hover:bg-hover desk:min-h-[38px] desk:px-5 desk:text-[13.5px]"
    >
      <span className="min-w-0 flex-1 truncate">{p.name}</span>
      <span className="hidden w-16 text-[12px] text-ink3 desk:block">{STATUS[p.status]}</span>
      <span className="hidden w-28 text-[12px] text-ink3 desk:block">
        {p.target_date ? formatShort(p.target_date, today) : ""}
      </span>
      <span className="text-[12px] text-ink3">
        <ProgressBar done={p.progress_done} total={p.progress_total} />
      </span>
    </Link>
  );
}

function Projects() {
  const areas = useAreas().data ?? [];
  const projects = useProjects().data ?? [];
  const today = useToday();
  usePageContext({}, []);
  return (
    <div className="mx-auto max-w-[920px] pb-10">
      <PageHeader title="Projects" sub={`${projects.length} projects in ${areas.length} areas`} />
      {[...areas, null].map((area) => {
        const own = projects.filter((p) => p.area_id === (area?.id ?? null));
        if (!area && !own.length) return null;
        return (
          <section key={area?.id ?? "none"} className="mt-6">
            <h2 className="flex items-center gap-2 border-b border-line px-4 pb-1.5 text-[13px] font-semibold desk:px-5">
              {area ? (
                <Link
                  to="/areas/$areaId"
                  params={{ areaId: area.id }}
                  className="inline-flex items-center gap-2 hover:text-accent"
                >
                  <Dot color={area.color} />
                  {area.name}
                </Link>
              ) : (
                "No area"
              )}
            </h2>
            {own.length ? (
              own.map((p) => <ProjectLine key={p.id} p={p} today={today} />)
            ) : (
              <p className="px-5 py-3 text-[13px] text-ink3">No projects yet.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
