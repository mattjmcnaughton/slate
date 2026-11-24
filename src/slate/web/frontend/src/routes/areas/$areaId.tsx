import { createFileRoute } from "@tanstack/react-router";
import { QuickAdd } from "../../components/QuickAdd";
import {
  Empty,
  type Group,
  PageHeader,
  TaskGroups,
  usePageContext,
} from "../../components/TaskList";
import { Dot } from "../../components/icons";
import { useAreas, useLookups, useTasks } from "../../lib/queries";

export const Route = createFileRoute("/areas/$areaId")({
  component: AreaPage,
});

function AreaPage() {
  const { areaId } = Route.useParams();
  const lookups = useLookups();
  const area = lookups.areas.get(areaId);
  const loaded = useAreas().isSuccess;
  const id = area?.id ?? "";
  const { data } = useTasks({ area_id: id, top_level: true, sort: "due" }, Boolean(area));
  usePageContext({ areaId: id, projectId: null }, [id]);
  if (!area) return loaded ? <Empty title="This area does not exist" /> : null;

  const projects = [...lookups.projects.values()].filter((p) => p.area_id === id);
  const groups: Group[] = [
    { key: "direct", title: area.name, tasks: (data ?? []).filter((t) => !t.project_id) },
    ...projects.map((p) => ({
      key: `p${p.id}`,
      title: p.name,
      tasks: (data ?? []).filter((t) => t.project_id === p.id),
    })),
  ];
  return (
    <div className="mx-auto max-w-[920px]">
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2.5">
            <Dot color={area.color} size={10} />
            {area.name}
          </span>
        }
        sub={`${data?.length ?? 0} open tasks across ${projects.length} projects`}
      >
        <div className="-mx-1 mt-4 desk:-mx-2">
          <QuickAdd variant="inline" placeholder={`Add to ${area.name}`} />
        </div>
      </PageHeader>
      {data && (
        <TaskGroups groups={groups} hideWhere empty={<Empty title="Nothing open in this area" />} />
      )}
    </div>
  );
}
