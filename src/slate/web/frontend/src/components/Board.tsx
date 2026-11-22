import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useState } from "react";
import { useTaskActions } from "../lib/actions";
import type { Task, TaskStatus } from "../lib/api";
import { type Lookups, useLookups, useToday } from "../lib/queries";
import { useUI } from "../stores/ui";
import { Counts, DueChip, LabelChips } from "./TaskMeta";
import { useVisibleIds } from "./TaskRow";
import { IconRepeat, PriorityIcon, STATUSES, StatusIcon } from "./icons";

type Lane = "recurring" | "tasks";

function Card({
  task,
  lookups,
  today,
  overlay,
}: { task: Task; lookups: Lookups; today?: string; overlay?: boolean }) {
  const selected = useUI((s) => s.selectedId === task.id);
  const open = useUI((s) => s.detailId === task.id);
  return (
    <div
      className={`rounded-md border bg-panel px-2.5 py-2 text-[13px] ${
        overlay
          ? "rotate-[1.5deg] border-line2 shadow-[var(--shadow)]"
          : open
            ? "border-accent/60"
            : selected
              ? "border-line2"
              : "border-line"
      }`}
    >
      <div className="flex items-center gap-1.5 text-[11.5px] tabular-nums text-ink3">
        <span>{task.key}</span>
        <span className="flex-1" />
        <PriorityIcon priority={task.priority} size={12} />
      </div>
      <div className="mt-1 flex gap-1.5">
        <span className="mt-[2px]">
          <StatusIcon status={task.status} size={13} />
        </span>
        <span
          className={`line-clamp-2 leading-snug ${task.status === "done" || task.status === "canceled" ? "text-ink3" : "text-ink"}`}
        >
          {task.title}
        </span>
      </div>
      {Boolean(
        task.due_date || task.label_ids.length || task.subtask_count || task.comment_count,
      ) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <DueChip task={task} today={today} />
          <Counts task={task} />
          <LabelChips ids={task.label_ids} lookups={lookups} max={2} />
        </div>
      )}
    </div>
  );
}

function DraggableCard({ task, lookups, today }: { task: Task; lookups: Lookups; today?: string }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.id,
    data: { task },
  });
  return (
    <div
      ref={setNodeRef}
      data-task-id={task.id}
      {...attributes}
      {...listeners}
      onClick={() => useUI.getState().openDetail(task.id)}
      onMouseMove={() =>
        useUI.getState().selectedId !== task.id && useUI.getState().select(task.id)
      }
      className={`touch-manipulation cursor-grab outline-none ${isDragging ? "opacity-30" : ""}`}
      aria-roledescription="Draggable task"
    >
      <Card task={task} lookups={lookups} today={today} />
    </div>
  );
}

const COL = "min-w-[184px] max-w-[320px] flex-1 basis-0";

function Column({
  lane,
  status,
  tasks,
  lookups,
  today,
  blocked,
  dragging,
}: {
  lane: Lane;
  status: TaskStatus;
  tasks: Task[];
  lookups: Lookups;
  today?: string;
  blocked: boolean;
  dragging: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `${lane}:${status}`, disabled: blocked });
  return (
    <div
      ref={setNodeRef}
      className={`${COL} flex min-h-[64px] flex-col gap-1.5 rounded-lg p-1.5 transition-colors ${
        isOver ? "bg-accent-soft" : dragging && blocked ? "bg-line/20 opacity-40" : "bg-line/30"
      }`}
    >
      {tasks.map((t) => (
        <DraggableCard key={t.id} task={t} lookups={lookups} today={today} />
      ))}
      {lane === "recurring" && status === "done" && (
        <p className="px-1.5 py-1 text-[11.5px] leading-snug text-ink3">
          Repeating tasks finish a run with E and move to their next date.
        </p>
      )}
    </div>
  );
}

export function Board({ tasks }: { tasks: Task[] }) {
  const lookups = useLookups();
  const today = useToday();
  const actions = useTaskActions();
  const [active, setActive] = useState<Task | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 220, tolerance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const recurring = tasks.filter((t) => t.recurrence);
  const plain = tasks.filter((t) => !t.recurrence);
  const by = (list: Task[], s: TaskStatus) => list.filter((t) => t.status === s);
  useVisibleIds([
    ...STATUSES.flatMap((s) => by(recurring, s.value).map((t) => t.id)),
    ...STATUSES.flatMap((s) => by(plain, s.value).map((t) => t.id)),
  ]);

  const onStart = (e: DragStartEvent) => setActive((e.active.data.current?.task as Task) ?? null);
  const onEnd = (e: DragEndEvent) => {
    setActive(null);
    const task = e.active.data.current?.task as Task | undefined;
    const over = e.over?.id ? String(e.over.id) : null;
    if (!task || !over) return;
    const status = over.split(":")[1] as TaskStatus;
    if (status === task.status) return;
    if (task.recurrence && status === "done") {
      useUI.getState().toast({
        tone: "warn",
        message: "Repeating tasks cannot be moved to Done. Press E to finish this run.",
      });
      return;
    }
    actions.setStatus([task.id], status);
  };

  const draggingRecurring = Boolean(active?.recurrence);
  return (
    <DndContext
      sensors={sensors}
      onDragStart={onStart}
      onDragEnd={onEnd}
      onDragCancel={() => setActive(null)}
    >
      <div className="scroll-thin overflow-x-auto px-4 pb-8 pt-3 desk:px-5">
        <div className="min-w-[980px]">
          <div className="mb-1 flex gap-2.5">
            {STATUSES.map((s) => (
              <div
                key={s.value}
                className={`${COL} flex h-7 items-center gap-2 px-2 text-[12.5px] font-medium text-ink2`}
              >
                <StatusIcon status={s.value} />
                {s.label}
                <span className="font-normal tabular-nums text-ink3">
                  {by(tasks, s.value).length}
                </span>
              </div>
            ))}
          </div>
          {recurring.length > 0 && (
            <>
              <div className="mb-1.5 mt-1 flex items-center gap-1.5 px-0.5 text-[12px] text-ink2">
                <IconRepeat size={13} className="text-teal" />
                Recurring
                <span className="text-ink3">not counted in progress</span>
              </div>
              <div className="mb-4 flex gap-2.5">
                {STATUSES.map((s) => (
                  <Column
                    key={s.value}
                    lane="recurring"
                    status={s.value}
                    tasks={by(recurring, s.value)}
                    lookups={lookups}
                    today={today}
                    blocked={s.value === "done" || (active !== null && !active.recurrence)}
                    dragging={active !== null}
                  />
                ))}
              </div>
              <div className="mb-1.5 px-0.5 text-[12px] text-ink2">Tasks</div>
            </>
          )}
          <div className="flex gap-2.5">
            {STATUSES.map((s) => (
              <Column
                key={s.value}
                lane="tasks"
                status={s.value}
                tasks={by(plain, s.value)}
                lookups={lookups}
                today={today}
                blocked={draggingRecurring && s.value === "done"}
                dragging={active !== null}
              />
            ))}
          </div>
        </div>
      </div>
      <DragOverlay dropAnimation={null}>
        {active ? <Card task={active} lookups={lookups} today={today} overlay /> : null}
      </DragOverlay>
    </DndContext>
  );
}
