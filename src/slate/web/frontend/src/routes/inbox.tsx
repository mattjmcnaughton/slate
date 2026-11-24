import { createFileRoute } from "@tanstack/react-router";
import { QuickAdd } from "../components/QuickAdd";
import { Empty, PageHeader, TaskGroups, usePageContext } from "../components/TaskList";
import { useTasks } from "../lib/queries";

export const Route = createFileRoute("/inbox")({
  component: Inbox,
});

function Inbox() {
  const { data } = useTasks({ inbox: true, top_level: true, sort: "created", order: "desc" });
  usePageContext({ projectId: null, areaId: null }, []);
  return (
    <div className="mx-auto max-w-[920px]">
      <PageHeader title="Inbox" sub="Tasks without a project or area. Press M to file one.">
        <div className="-mx-1 mt-4 desk:-mx-2">
          <QuickAdd variant="inline" />
        </div>
      </PageHeader>
      {data && (
        <TaskGroups
          groups={[{ key: "inbox", tasks: data }]}
          empty={<Empty title="Inbox zero" body="New tasks without a #project land here." />}
        />
      )}
    </div>
  );
}
