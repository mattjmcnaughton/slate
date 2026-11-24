import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { type ParseResult, api } from "../lib/api";
import { formatDue, formatTime } from "../lib/dates";
import { qk, useLookups, useParse, usePatchTask, useQuickAdd, useToday } from "../lib/queries";
import { buildSpans } from "../lib/tokens";
import { useUI } from "../stores/ui";
import {
  Dot,
  IconPlus,
  IconRepeat,
  PriorityIcon,
  StatusIcon,
  priorityLabel,
  statusLabel,
} from "./icons";

/** Token colors, as [text var, tint var]. */
const TOKEN_COLOR: Record<string, string> = {
  date: "--accent",
  recurrence: "--teal",
  project: "--blue",
  label: "--amber",
  priority: "--red",
  status: "--plum",
};

export function tokenStyle(kind: string, unresolved: boolean): React.CSSProperties {
  const v = TOKEN_COLOR[kind] ?? "--ink2";
  const color = unresolved ? "--red" : v;
  return {
    color: `rgb(var(${color}))`,
    background: `rgb(var(${color}) / 0.13)`,
    boxShadow: `0 0 0 2px rgb(var(${color}) / 0.13)`,
    borderRadius: 3,
    textDecoration: unresolved ? "underline dashed" : undefined,
    textUnderlineOffset: 3,
  };
}

interface Props {
  variant: "inline" | "modal" | "subtask";
  /** Overrides the page defaults (used for subtasks). */
  defaults?: { projectId?: string | null; areaId?: string | null; parentId?: string };
  onDone?: () => void;
  autoFocus?: boolean;
  placeholder?: string;
}

export function QuickAdd({ variant, defaults, onDone, autoFocus, placeholder }: Props) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const page = useUI((s) => s.page);
  const toast = useUI((s) => s.toast);
  const quickAdd = useQuickAdd();
  const patch = usePatchTask();
  const today = useToday();
  const parsed = useParse(text);
  const data = text.trim() ? parsed.data : undefined;
  const spans = buildSpans(text, data?.tokens ?? []);

  // Let the global "c" key focus this line instead of opening the modal.
  useEffect(() => {
    if (variant !== "inline") return;
    const focus = () => inputRef.current?.focus();
    useUI.getState().setInlineQuickAdd(focus);
    return () => {
      if (useUI.getState().inlineQuickAdd === focus) useUI.getState().setInlineQuickAdd(null);
    };
  }, [variant]);

  const syncScroll = () => {
    if (overlayRef.current && inputRef.current) {
      overlayRef.current.scrollLeft = inputRef.current.scrollLeft;
    }
  };

  const submit = async () => {
    const value = text;
    if (!value.trim() || quickAdd.isPending) return;
    // The debounced preview may lag the last keystroke; parse the exact text.
    let fresh: ParseResult;
    try {
      fresh = await qc.fetchQuery({
        queryKey: qk.parse(value),
        queryFn: () => api.parse(value),
        staleTime: 30_000,
      });
    } catch {
      return;
    }
    if (!fresh.title.trim()) {
      toast({ tone: "error", message: "Add a title as well as the date, project, or labels." });
      return;
    }
    const projectId = defaults?.projectId !== undefined ? defaults.projectId : page.projectId;
    const areaId = defaults?.areaId !== undefined ? defaults.areaId : page.areaId;
    quickAdd.mutate(
      {
        text: value,
        create_missing: Boolean(fresh.unknown_project || fresh.unknown_labels.length),
        project_id: projectId ?? null,
        area_id: projectId ? null : (areaId ?? null),
        parent_id: defaults?.parentId ?? null,
      },
      {
        onSuccess: (task) => {
          // On Today, a task typed without a date belongs to today.
          if (page.dueToday && !defaults?.parentId && !task.due_date && today) {
            patch.mutate({ id: task.id, patch: { due_date: today } });
          }
          if (variant !== "subtask") toast({ message: `Added ${task.key}` });
          if (fresh.unknown_project) qc.invalidateQueries({ queryKey: qk.projects });
          setText("");
          onDone?.();
        },
      },
    );
  };

  const compact = variant === "subtask";
  const textCls = compact ? "text-[13px]" : "text-[15px] desk:text-[14px]";
  const pad = compact ? "py-1.5 pl-7 pr-2" : "py-2.5 pl-9 pr-3";

  return (
    <div className={variant === "inline" ? "group" : ""}>
      <div
        className={`relative flex items-center rounded-md ${
          variant === "modal"
            ? ""
            : "border border-transparent hover:border-line focus-within:border-line2 focus-within:bg-panel"
        }`}
      >
        <span
          className={`pointer-events-none absolute text-ink3 group-focus-within:text-accent ${
            compact ? "left-1.5" : "left-3"
          }`}
        >
          <IconPlus size={compact ? 14 : 16} />
        </span>
        <div
          ref={overlayRef}
          aria-hidden
          className={`pointer-events-none absolute inset-0 overflow-hidden whitespace-pre ${pad} ${textCls} text-ink`}
        >
          {spans.map((s) =>
            s.kind ? (
              <span key={s.start} style={tokenStyle(s.kind, s.unresolved)}>
                {s.text}
              </span>
            ) : (
              <span key={s.start}>{s.text}</span>
            ),
          )}
        </div>
        <input
          ref={inputRef}
          value={text}
          // biome-ignore lint/a11y/noAutofocus: the modal and subtask line open to type
          autoFocus={autoFocus}
          aria-label="Add a task"
          spellCheck={false}
          autoComplete="off"
          placeholder={placeholder ?? "Add a task: Call Sam fri 5pm #home p2"}
          onChange={(e) => {
            setText(e.target.value);
            requestAnimationFrame(syncScroll);
          }}
          onScroll={syncScroll}
          onKeyUp={syncScroll}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            } else if (e.key === "Escape" && variant !== "modal") {
              e.preventDefault();
              if (text) setText("");
              else e.currentTarget.blur();
            }
          }}
          className={`relative w-full bg-transparent text-transparent caret-[rgb(var(--ink))] outline-none ${pad} ${textCls}`}
        />
      </div>
      {data && text.trim() && <Preview data={data} today={today} compact={compact} />}
    </div>
  );
}

function Preview({
  data,
  today,
  compact,
}: {
  data: ParseResult;
  today?: string;
  compact: boolean;
}) {
  const lookups = useLookups();
  const project = data.project_id ? lookups.projects.get(data.project_id) : undefined;
  const area = data.area_id ? lookups.areas.get(data.area_id) : undefined;
  const items: React.ReactNode[] = [];

  if (data.due_date && today) {
    items.push(
      <span key="due" className="chip" style={tokenStyle("date", false)}>
        {formatDue(data.due_date, today)}
        {data.due_time ? ` ${formatTime(data.due_time)}` : ""}
      </span>,
    );
  }
  if (data.recurrence) {
    items.push(
      <span key="rec" className="chip" style={tokenStyle("recurrence", false)}>
        <IconRepeat size={12} />
        {data.recurrence.text}
        {data.recurrence.mode === "after_completion" ? " after done" : ""}
      </span>,
    );
  }
  if (project || area) {
    items.push(
      <span key="where" className="chip">
        <Dot color={project?.color ?? area?.color ?? "rgb(var(--ink3))"} size={7} />
        {project?.name ?? area?.name}
      </span>,
    );
  }
  if (data.unknown_project) {
    items.push(
      <span key="newp" className="chip border-dashed" style={tokenStyle("project", false)}>
        Create project ‘{data.unknown_project}’
      </span>,
    );
  }
  for (const id of data.label_ids) {
    const l = lookups.labels.get(id);
    if (l)
      items.push(
        <span key={`l${id}`} className="chip">
          <Dot color={l.color} size={6} />
          {l.name}
        </span>,
      );
  }
  for (const name of data.unknown_labels) {
    items.push(
      <span key={`nl${name}`} className="chip border-dashed" style={tokenStyle("label", false)}>
        Create label ‘{name}’
      </span>,
    );
  }
  if (data.priority) {
    items.push(
      <span key="pri" className="chip">
        <PriorityIcon priority={data.priority} size={12} />
        {priorityLabel(data.priority)}
      </span>,
    );
  }
  if (data.status) {
    items.push(
      <span key="st" className="chip">
        <StatusIcon status={data.status} size={12} />
        {statusLabel(data.status)}
      </span>,
    );
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-1.5 pb-1 ${compact ? "pl-7 pt-1" : "pl-9 pt-1.5"}`}
    >
      <span className="mr-0.5 max-w-[22rem] truncate text-[12.5px] text-ink2">
        {data.title || <span className="text-ink3">Needs a title</span>}
      </span>
      {items}
      <span className="ml-auto hidden items-center gap-1 text-[11.5px] text-ink3 desk:flex">
        <kbd className="kbd">↵</kbd> to add
      </span>
    </div>
  );
}

/** The quick-add dialog for "c" where the page has no inline line, and the phone + button. */
export function QuickAddModal() {
  const open = useUI((s) => s.quickAdd);
  const close = () => useUI.getState().setQuickAdd(false);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/20 desk:items-start desk:pt-[16vh]">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 cursor-default"
        onClick={close}
      />
      <div
        role="dialog"
        aria-label="Add a task"
        className="popover anim-sheet relative w-full rounded-b-none px-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 desk:anim-rise desk:w-[620px] desk:rounded-lg desk:pb-2"
      >
        <QuickAdd variant="modal" autoFocus onDone={close} />
      </div>
    </div>
  );
}
