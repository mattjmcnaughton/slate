import { createFileRoute } from "@tanstack/react-router";
import { PendingCard, applyInput } from "../components/Assistant";
import { Empty, PageHeader, usePageContext } from "../components/TaskList";
import { usePendingActions, usePendingChanges } from "../lib/queries";

export const Route = createFileRoute("/pending")({
  component: Pending,
});

function Pending() {
  const all = usePendingChanges().data ?? [];
  const { apply } = usePendingActions();
  usePageContext({}, []);
  const open = all.filter((p) => p.status === "pending").reverse();
  const recent = all
    .filter((p) => p.status !== "pending")
    .sort((a, b) => (b.resolved_at ?? "").localeCompare(a.resolved_at ?? ""))
    .slice(0, 20);
  return (
    <div className="mx-auto max-w-[760px] pb-10">
      <PageHeader
        title="Pending changes"
        sub="Drafted by the assistant or an MCP client. Nothing changes until you apply it."
      >
        {open.filter((p) => p.tool !== "delete_task").length > 1 && (
          <button
            type="button"
            onClick={() => {
              for (const p of open)
                if (p.tool !== "delete_task") apply.mutate({ id: p.id, input: applyInput(p) });
            }}
            className="mt-3 h-8 rounded-md bg-accent px-3 text-[13px] text-white dark:text-bg"
          >
            Apply all except deletes
          </button>
        )}
      </PageHeader>
      <div className="mt-4 flex flex-col gap-2.5 px-4 desk:px-5">
        {open.length === 0 && (
          <Empty title="Nothing waiting" body="Changes the assistant drafts show up here." />
        )}
        {open.map((p) => (
          <PendingCard key={p.id} change={p} />
        ))}
        {recent.length > 0 && (
          <>
            <div className="mt-6 text-[12px] font-medium text-ink3">Recently resolved</div>
            {recent.map((p) => (
              <PendingCard key={p.id} change={p} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
