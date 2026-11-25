import type { Meta, StoryObj } from "@storybook/react-vite";
import { Board } from "../components/Board";
import { QuickAdd } from "../components/QuickAdd";
import { Empty, PageHeader, TaskGroups } from "../components/TaskList";
import { Counts, DueChip, LabelChips, ProgressBar, Where } from "../components/TaskMeta";
import { TaskRow } from "../components/TaskRow";
import { PRIORITIES, PriorityIcon, STATUSES, StatusIcon } from "../components/icons";
import { useLookups, useTasks, useToday } from "../lib/queries";
import { lid, pid, tid } from "./mockApi";

/** Building blocks on their own, fed by the same mock API as the screens. */
const meta: Meta = { title: "Components" };
export default meta;
type Story = StoryObj;

function Rows({ ids }: { ids: string[] }) {
  const lookups = useLookups();
  const today = useToday();
  const { data } = useTasks({ top_level: true, include_closed: true, sort: "due" });
  return (
    <div className="max-w-[920px] overflow-hidden rounded-md border border-line">
      {data
        ?.filter((t) => ids.includes(t.id))
        .map((t) => (
          <TaskRow key={t.id} task={t} today={today} lookups={lookups} />
        ))}
    </div>
  );
}

/** Overdue, due today with a time, labels, comments and subtasks, recurring, done, canceled. */
export const TaskRows: Story = {
  render: () => (
    <Rows ids={[tid(2), tid(28), tid(10), tid(24), tid(8), tid(4), tid(35), tid(17), tid(3)]} />
  ),
};
export const TaskRowsDark: Story = { ...TaskRows, globals: { theme: "dark" } };
export const TaskRowSelectedAndChecked: Story = {
  render: () => <Rows ids={[tid(1), tid(2), tid(4)]} />,
  parameters: { slate: { ui: { selectedId: tid(2), checkedIds: [tid(1), tid(2)] } } },
};

function Grouped() {
  const { data } = useTasks({
    project_id: pid(3),
    top_level: true,
    include_closed: true,
    sort: "due",
  });
  if (!data) return null;
  return (
    <div className="max-w-[920px]">
      <TaskGroups
        groups={STATUSES.map((s) => ({
          key: s.value,
          title: s.label,
          tasks: data.filter((t) => t.status === s.value),
        }))}
      />
    </div>
  );
}
export const GroupedList: Story = { render: () => <Grouped /> };
export const EmptyState: Story = {
  render: () => <Empty title="All clear for today" body="Press C to add a task." />,
};

function KitchenBoard() {
  const { data } = useTasks({ project_id: pid(1), top_level: true, include_closed: true });
  return data ? <Board tasks={data} /> : null;
}
function MarathonBoard() {
  const { data } = useTasks({ project_id: pid(2), top_level: true, include_closed: true });
  return data ? <Board tasks={data} /> : null;
}
export const ProjectBoard: Story = { render: () => <KitchenBoard /> };
/** A project with repeating tasks gets a Recurring lane above the tasks. */
export const ProjectBoardWithRecurring: Story = { render: () => <MarathonBoard /> };
export const ProjectBoardDark: Story = { ...ProjectBoardWithRecurring, globals: { theme: "dark" } };

function TypedQuickAdd({ text }: { text: string }) {
  return (
    <div
      className="max-w-[620px]"
      ref={(el) => {
        const input = el?.querySelector("input");
        if (!input || input.value) return;
        // Type through React's setter so the live parse preview runs.
        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
        set?.call(input, text);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }}
    >
      <QuickAdd variant="inline" />
    </div>
  );
}
export const QuickAddInline: Story = {
  render: () => (
    <div className="max-w-[620px]">
      <QuickAdd variant="inline" />
    </div>
  ),
};
/** Type a line to see tokens highlighted and the parse preview. */
export const QuickAddParsing: Story = {
  render: () => <TypedQuickAdd text="Call Sam fri 5pm #kitchen @calls p2" />,
};
export const QuickAddParsingDark: Story = { ...QuickAddParsing, globals: { theme: "dark" } };
export const QuickAddNewProjectAndLabel: Story = {
  render: () => <TypedQuickAdd text="Book flights tomorrow #japan-trip @travel" />,
};

function MetaSheet() {
  const lookups = useLookups();
  const today = useToday();
  const { data } = useTasks({ top_level: true, include_closed: true });
  const t = (n: number) => data?.find((x) => x.id === tid(n));
  if (!data || !today) return null;
  const row = (label: string, node: React.ReactNode) => (
    <div className="flex items-center gap-4 text-[13px]">
      <span className="w-40 text-ink3">{label}</span>
      {node}
    </div>
  );
  return (
    <div className="space-y-3">
      {row(
        "Status",
        <span className="flex gap-3">
          {STATUSES.map((s) => (
            <StatusIcon key={s.value} status={s.value} />
          ))}
        </span>,
      )}
      {row(
        "Priority",
        <span className="flex gap-3">
          {PRIORITIES.map((p) => (
            <PriorityIcon key={p.value} priority={p.value} />
          ))}
        </span>,
      )}
      {row(
        "Due overdue / today / soon",
        <span className="flex gap-3">
          {[2, 28, 4, 31].map((id) => {
            const x = t(id);
            return x && <DueChip key={id} task={x} today={today} />;
          })}
        </span>,
      )}
      {row("Due recurring", t(8) && <DueChip task={t(8) as never} today={today} />)}
      {row("Labels", <LabelChips ids={[1, 2, 3, 4].map(lid)} lookups={lookups} max={4} />)}
      {row(
        "Project / area",
        <span className="flex gap-3">
          {[10, 5].map((id) => {
            const x = t(id);
            return x && <Where key={id} task={x} lookups={lookups} />;
          })}
        </span>,
      )}
      {row("Comments and subtasks", t(10) && <Counts task={t(10) as never} />)}
      {row("Progress", <ProgressBar done={3} total={7} />)}
    </div>
  );
}
export const TaskMeta: Story = { render: () => <MetaSheet /> };
export const TaskMetaDark: Story = { ...TaskMeta, globals: { theme: "dark" } };

export const PageHeaders: Story = {
  render: () => (
    <div className="max-w-[920px] space-y-8">
      <PageHeader serif title="Monday, November 23" sub="4 to do, 2 overdue, 1 done" />
      <PageHeader title="Kitchen refresh" sub="Home · Active · Target Thu, Dec 17" />
    </div>
  ),
};
