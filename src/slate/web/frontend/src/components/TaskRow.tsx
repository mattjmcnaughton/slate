import { useEffect, useRef, useState } from "react";
import type { Task } from "../lib/api";
import { type Lookups, useToggleComplete } from "../lib/queries";
import { useUI } from "../stores/ui";
import { Counts, DueChip, LabelChips, Where } from "./TaskMeta";
import { IconCalendar, IconCheck, IconRepeat, PriorityIcon, StatusIcon } from "./icons";

interface Props {
  task: Task;
  today?: string;
  lookups: Lookups;
  /** Hide the project/area chip (on its own project page). */
  hideWhere?: boolean;
  /** Hide the due chip (inside a day group where the date is implied). */
  hideDue?: boolean;
}

const SWIPE = 72;

export function TaskRow({ task, today, lookups, hideWhere, hideDue }: Props) {
  const selected = useUI((s) => s.selectedId === task.id);
  const checked = useUI((s) => s.checkedIds.includes(task.id));
  const open = useUI((s) => s.detailId === task.id);
  const toggle = useToggleComplete();
  const ref = useRef<HTMLDivElement>(null);
  const closed = task.status === "done" || task.status === "canceled";
  const [dx, setDxState] = useState(0);
  const dxRef = useRef(0);
  const setDx = (v: number) => {
    dxRef.current = v;
    setDxState(v);
  };
  const start = useRef<{ x: number; y: number; locked: boolean | null } | null>(null);

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const openTask = () => useUI.getState().openDetail(task.id);

  // Phone: swipe right to complete, swipe left for the date sheet.
  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    start.current = { x: t.clientX, y: t.clientY, locked: null };
  };
  const onTouchMove = (e: React.TouchEvent) => {
    const s = start.current;
    if (!s) return;
    const t = e.touches[0];
    const mx = t.clientX - s.x;
    const my = t.clientY - s.y;
    if (s.locked === null && (Math.abs(mx) > 8 || Math.abs(my) > 8)) {
      s.locked = Math.abs(mx) > Math.abs(my) * 1.3;
    }
    if (s.locked) setDx(Math.max(-120, Math.min(120, mx)));
  };
  const onTouchEnd = () => {
    const moved = dxRef.current;
    if (moved >= SWIPE) toggle(task.id);
    if (moved <= -SWIPE) useUI.getState().openMenu({ kind: "due", taskIds: [task.id] });
    start.current = null;
    setDx(0);
  };

  return (
    <div className="relative overflow-hidden" data-task-id={task.id}>
      {dx !== 0 && (
        <div
          className={`absolute inset-0 flex items-center px-5 text-white ${
            dx > 0 ? "justify-start bg-accent" : "justify-end bg-blue"
          }`}
          style={{ opacity: Math.min(1, Math.abs(dx) / SWIPE) }}
        >
          {dx > 0 ? <IconCheck size={18} /> : <IconCalendar size={18} />}
        </div>
      )}
      <div
        ref={ref}
        role="button"
        tabIndex={-1}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey) {
            useUI.getState().toggleChecked(task.id);
            useUI.getState().select(task.id);
            return;
          }
          openTask();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") openTask();
        }}
        onMouseMove={() => {
          if (!selected) useUI.getState().select(task.id);
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        style={{ transform: dx ? `translateX(${dx}px)` : undefined }}
        className={`group relative flex min-h-[44px] cursor-default select-none items-center gap-2.5 border-b border-line/70 px-4 desk:min-h-[36px] desk:gap-2 desk:px-5 ${
          dx === 0 ? "transition-transform" : ""
        } ${open || checked ? "row-open" : selected ? "bg-hover" : "bg-panel"}`}
      >
        {(selected || checked) && (
          <span className="absolute inset-y-0 left-0 w-[2px] bg-accent" aria-hidden />
        )}
        <span className="hidden w-[52px] shrink-0 text-[12px] tabular-nums text-ink3 desk:block">
          {task.key}
        </span>
        <span className="hidden desk:block" title="Priority">
          <PriorityIcon priority={task.priority} />
        </span>
        <button
          type="button"
          aria-label={closed ? `Reopen ${task.title}` : `Complete ${task.title}`}
          onClick={(e) => {
            e.stopPropagation();
            toggle(task.id);
          }}
          className="-m-1.5 rounded-full p-1.5 hover:bg-line/60"
        >
          <span className="block desk:hidden">
            <StatusIcon status={task.status} size={18} />
          </span>
          <span className="hidden desk:block">
            <StatusIcon status={task.status} />
          </span>
        </button>
        <span
          className={`min-w-0 flex-1 truncate text-[15px] desk:text-[13.5px] ${
            closed ? "text-ink3 line-through decoration-ink3/50" : "text-ink"
          }`}
        >
          {task.title}
        </span>
        <span className="flex shrink-0 items-center gap-2.5">
          <span className="hidden items-center gap-2.5 desk:flex">
            <Counts task={task} />
            <LabelChips ids={task.label_ids} lookups={lookups} />
          </span>
          {!hideWhere && (
            <span className="hidden desk:inline-flex">
              <Where task={task} lookups={lookups} />
            </span>
          )}
          {hideDue ? (
            task.recurrence && (
              <span className="text-ink3" title={task.recurrence.text}>
                <IconRepeat size={12} />
              </span>
            )
          ) : (
            <DueChip task={task} today={today} />
          )}
          {task.priority === 1 && (
            <span className="desk:hidden">
              <PriorityIcon priority={1} size={12} />
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

/** Register the ids the keyboard cursor walks over (in display order). */
export function useVisibleIds(ids: number[]) {
  const key = ids.join(",");
  // biome-ignore lint/correctness/useExhaustiveDependencies: keyed by the joined ids
  useEffect(() => {
    const ui = useUI.getState();
    const prev = ui.visibleIds;
    ui.setVisible(ids);
    if (ui.selectedId !== null && !ids.includes(ui.selectedId)) {
      // The row left the list (completed, moved): keep the cursor at the same position.
      const at = prev.indexOf(ui.selectedId);
      ui.select(at >= 0 && ids.length ? ids[Math.min(at, ids.length - 1)] : null);
    }
  }, [key]);
  useEffect(() => () => useUI.getState().setVisible([]), []);
}
