import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useTaskActions } from "../lib/actions";
import { describeActivity } from "../lib/activity";
import type { Activity, Comment, Task } from "../lib/api";
import { formatDue, formatRelative, formatTime } from "../lib/dates";
import { keyLabels } from "../lib/keys";
import {
  useActivity,
  useCommentMutations,
  useComments,
  useLookups,
  usePatchTask,
  useTask,
  useTasks,
  useToday,
  useToggleComplete,
} from "../lib/queries";
import type { MenuKind } from "../stores/ui";
import { useUI } from "../stores/ui";
import { QuickAdd } from "./QuickAdd";
import { TaskRow } from "./TaskRow";
import {
  Dot,
  IconBack,
  IconCalendar,
  IconClose,
  IconInbox,
  IconRepeat,
  IconTrash,
  PriorityIcon,
  StatusIcon,
  priorityLabel,
  statusLabel,
} from "./icons";

const Markdown = lazy(() => import("react-markdown"));

function Md({ children }: { children: string }) {
  return (
    <Suspense fallback={<p className="whitespace-pre-wrap">{children}</p>}>
      <Markdown>{children}</Markdown>
    </Suspense>
  );
}

export function TaskDetail({ id, phone }: { id: string; phone: boolean }) {
  const { data: task, isError } = useTask(id);
  const close = () => useUI.getState().closeDetail();

  return (
    <aside
      aria-label="Task detail"
      className={
        phone
          ? "anim-sheet fixed inset-0 z-40 flex flex-col bg-panel"
          : "anim-pane flex h-full w-[min(520px,44vw)] shrink-0 flex-col border-l border-line bg-panel"
      }
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-3 pt-[env(safe-area-inset-top)] desk:px-4">
        {phone && (
          <button type="button" aria-label="Back" onClick={close} className="-ml-1 p-1.5 text-ink2">
            <IconBack size={18} />
          </button>
        )}
        <span className="text-[12.5px] tabular-nums text-ink3">{task?.key ?? `SLT-${id}`}</span>
        {task?.parent_id && (
          <button
            type="button"
            className="text-[12.5px] text-ink3 hover:text-accent"
            onClick={() => useUI.getState().openDetail(task.parent_id as string)}
          >
            subtask of {task.parent_key}
          </button>
        )}
        <span className="flex-1" />
        {task && <DeleteButton task={task} />}
        {!phone && (
          <button
            type="button"
            aria-label="Close detail"
            onClick={close}
            className="rounded p-1.5 text-ink3 hover:bg-hover hover:text-ink"
          >
            <IconClose size={15} />
          </button>
        )}
      </header>
      {isError && !task ? (
        <div className="p-6 text-[13px] text-ink3">This task no longer exists.</div>
      ) : !task ? (
        <div className="p-6 text-[13px] text-ink3">Loading…</div>
      ) : (
        <div className="scroll-thin flex-1 overflow-y-auto pb-[max(2rem,env(safe-area-inset-bottom))]">
          <DetailBody key={task.id} task={task} />
        </div>
      )}
    </aside>
  );
}

function DeleteButton({ task }: { task: Task }) {
  const actions = useTaskActions();
  return (
    <button
      type="button"
      aria-label="Delete task"
      title="Delete"
      onClick={() => actions.confirmDelete([task.id])}
      className="rounded p-1.5 text-ink3 hover:bg-hover hover:text-red"
    >
      <IconTrash size={15} />
    </button>
  );
}

function DetailBody({ task }: { task: Task }) {
  const toggle = useToggleComplete();
  return (
    <div className="px-5 pt-4 desk:px-6">
      <div className="flex items-start gap-3">
        <button
          type="button"
          className="mt-[7px]"
          aria-label={task.status === "done" ? "Reopen" : "Complete"}
          onClick={() => toggle(task.id)}
        >
          <StatusIcon status={task.status} size={18} />
        </button>
        <Title task={task} />
      </div>
      <Properties task={task} />
      <Description task={task} />
      {!task.parent_id && <Subtasks task={task} />}
      <Timeline task={task} />
    </div>
  );
}

function Title({ task }: { task: Task }) {
  const patch = usePatchTask();
  const [value, setValue] = useState(task.title);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => setValue(task.title), [task.title]);
  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  });
  const save = () => {
    const v = value.trim();
    if (v && v !== task.title) patch.mutate({ id: task.id, patch: { title: v } });
    else setValue(task.title);
  };
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      aria-label="Title"
      onChange={(e) => setValue(e.target.value.replace(/\n/g, ""))}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.blur();
        } else if (e.key === "Escape") {
          e.stopPropagation();
          setValue(task.title);
          requestAnimationFrame(() => ref.current?.blur());
        }
      }}
      className={`min-w-0 flex-1 resize-none overflow-hidden rounded-md px-1 py-0.5 text-[20px] font-semibold leading-snug outline-none focus:bg-hover ${
        task.status === "done" ? "text-ink2" : "text-ink"
      }`}
    />
  );
}

function PropRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-[32px] items-center gap-3">
      <span className="w-20 shrink-0 text-[12.5px] text-ink3">{label}</span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">{children}</div>
    </div>
  );
}

function PropButton({
  kind,
  task,
  children,
}: {
  kind: MenuKind;
  task: Task;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        useUI
          .getState()
          .openMenu({ kind, taskIds: [task.id], anchor: { x: r.left, y: r.bottom + 4 } });
      }}
      className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[13px] text-ink hover:bg-hover"
    >
      {children}
    </button>
  );
}

function Properties({ task }: { task: Task }) {
  const lookups = useLookups();
  const today = useToday();
  const patch = usePatchTask();
  const project = task.project_id ? lookups.projects.get(task.project_id) : undefined;
  const area = project?.area_id
    ? lookups.areas.get(project.area_id)
    : task.area_id
      ? lookups.areas.get(task.area_id)
      : undefined;
  const labels = task.label_ids.map((l) => lookups.labels.get(l)).filter((l) => l !== undefined);

  return (
    <div className="mt-4 space-y-0.5 border-y border-line py-2.5">
      <PropRow label="Status">
        <PropButton kind="status" task={task}>
          <StatusIcon status={task.status} />
          {statusLabel(task.status)}
        </PropButton>
      </PropRow>
      <PropRow label="Priority">
        <PropButton kind="priority" task={task}>
          <PriorityIcon priority={task.priority} />
          {task.priority ? priorityLabel(task.priority) : <span className="text-ink3">None</span>}
        </PropButton>
      </PropRow>
      <PropRow label="Project">
        <PropButton kind="project" task={task}>
          {project || area ? (
            <>
              <Dot color={project?.color ?? area?.color ?? "rgb(var(--ink3))"} size={7} />
              {area && project && <span className="text-ink3">{area.name} /</span>}
              {project?.name ?? area?.name}
            </>
          ) : (
            <>
              <IconInbox size={14} className="text-ink3" />
              Inbox
            </>
          )}
        </PropButton>
      </PropRow>
      <PropRow label="Labels">
        <PropButton kind="labels" task={task}>
          {labels.length ? (
            labels.map((l) => (
              <span key={l.id} className="chip">
                <Dot color={l.color} size={6} />
                {l.name}
              </span>
            ))
          ) : (
            <span className="text-ink3">Add labels</span>
          )}
        </PropButton>
      </PropRow>
      <PropRow label="Due">
        <PropButton kind="due" task={task}>
          <IconCalendar size={14} className="text-ink3" />
          {task.due_date && today ? (
            <>
              {formatDue(task.due_date, today)}
              {task.due_time && <span className="text-ink2">{formatTime(task.due_time)}</span>}
            </>
          ) : (
            <span className="text-ink3">No date</span>
          )}
        </PropButton>
      </PropRow>
      <PropRow label="Repeat">
        <RepeatField
          task={task}
          onClear={() => patch.mutate({ id: task.id, patch: { clear_recurrence: true } })}
        />
      </PropRow>
    </div>
  );
}

function RepeatField({ task, onClear }: { task: Task; onClear: () => void }) {
  const patch = usePatchTask();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  if (task.parent_id)
    return <span className="px-2 text-[13px] text-ink3">Subtasks cannot repeat</span>;
  if (editing) {
    return (
      <input
        // biome-ignore lint/a11y/noAutofocus: opened by a click to type
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="every mon, every! 3 days"
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) {
            patch.mutate({ id: task.id, patch: { due_string: value.trim() } });
            setEditing(false);
          } else if (e.key === "Escape") {
            e.stopPropagation();
            setEditing(false);
          }
        }}
        className="h-7 w-full rounded-md bg-hover px-2 text-[13px] outline-none"
      />
    );
  }
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setValue(task.recurrence?.text ?? "");
          setEditing(true);
        }}
        className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[13px] hover:bg-hover"
      >
        <IconRepeat size={14} className="text-ink3" />
        {task.recurrence ? (
          <>
            {task.recurrence.text}
            {task.recurrence.mode === "after_completion" && (
              <span className="text-ink3">after done</span>
            )}
          </>
        ) : (
          <span className="text-ink3">Does not repeat</span>
        )}
      </button>
      {task.recurrence && (
        <>
          <span className="text-[12px] text-ink3">{task.completed_runs} done</span>
          <button
            type="button"
            onClick={onClear}
            className="ml-auto text-[12px] text-ink3 hover:text-red"
          >
            Stop repeating
          </button>
        </>
      )}
    </>
  );
}

function Description({ task }: { task: Task }) {
  const patch = usePatchTask();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(task.description);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!editing) setValue(task.description);
  }, [task.description, editing]);
  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.max(96, el.scrollHeight)}px`;
    }
  });
  const save = () => {
    setEditing(false);
    if (value !== task.description) patch.mutate({ id: task.id, patch: { description: value } });
  };

  return (
    <section className="mt-4">
      {editing ? (
        <>
          <textarea
            ref={ref}
            // biome-ignore lint/a11y/noAutofocus: opened by a click to type
            autoFocus
            value={value}
            aria-label="Description"
            onChange={(e) => setValue(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === "Escape" || (e.key === "Enter" && (e.metaKey || e.ctrlKey))) {
                e.preventDefault();
                e.stopPropagation();
                e.currentTarget.blur();
              }
            }}
            placeholder="Add notes in Markdown"
            className="w-full resize-none rounded-md border border-line2 bg-bg/50 p-2.5 font-mono text-[12.5px] leading-relaxed outline-none"
          />
          <p className="mt-1 text-[11.5px] text-ink3">
            Markdown. Esc or {keyLabels("mod+enter").join(" ")} to save.
          </p>
        </>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="block w-full rounded-md px-1 py-1 text-left text-[13.5px] hover:bg-hover/60"
        >
          {task.description.trim() ? (
            <div className="md">
              <Md>{task.description}</Md>
            </div>
          ) : (
            <span className="text-ink3">Add a description…</span>
          )}
        </button>
      )}
    </section>
  );
}

function Subtasks({ task }: { task: Task }) {
  const lookups = useLookups();
  const today = useToday();
  const { data: subs } = useTasks({ parent_id: task.id, include_closed: true, sort: "created" });
  const [adding, setAdding] = useState(false);
  return (
    <section className="mt-6">
      <div className="mb-1 flex items-center gap-2">
        <h3 className="text-[13px] font-semibold">Subtasks</h3>
        {task.subtask_count > 0 && (
          <span className="text-[12px] tabular-nums text-ink3">
            {task.subtask_count - task.open_subtask_count}/{task.subtask_count}
          </span>
        )}
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="text-[12.5px] text-ink3 hover:text-accent"
        >
          Add subtask
        </button>
      </div>
      <div className="overflow-hidden rounded-md border border-line [&>div:last-child>div]:border-b-0">
        {subs?.map((s) => (
          <TaskRow key={s.id} task={s} today={today} lookups={lookups} hideWhere />
        ))}
        {(adding || !subs?.length) && (
          <div className="bg-panel px-1 py-0.5">
            <QuickAdd
              variant="subtask"
              autoFocus={adding}
              placeholder="Add a subtask"
              defaults={{ parentId: task.id, projectId: task.project_id, areaId: task.area_id }}
            />
          </div>
        )}
      </div>
    </section>
  );
}

type Entry = { at: string; comment?: Comment; activity?: Activity };

function Timeline({ task }: { task: Task }) {
  const lookups = useLookups();
  const comments = useComments(task.id).data ?? [];
  const activity = useActivity(task.id).data ?? [];
  const { add } = useCommentMutations(task.id);
  const [draft, setDraft] = useState("");

  // "commented" entries are shown as the comment itself.
  const entries: Entry[] = [
    ...comments.map((c): Entry => ({ at: c.created_at, comment: c })),
    ...activity
      .filter((a) => a.kind !== "commented")
      .map((a): Entry => ({ at: a.created_at, activity: a })),
  ].sort(
    (a, b) =>
      Date.parse(a.at) - Date.parse(b.at) ||
      // Same instant: activity before comments, each in creation order.
      Number(Boolean(a.comment)) - Number(Boolean(b.comment)) ||
      // Ids are UUIDv7, so comparing them as strings is creation order.
      (a.activity?.id ?? a.comment?.id ?? "").localeCompare(b.activity?.id ?? b.comment?.id ?? ""),
  );

  const submit = () => {
    const body = draft.trim();
    if (!body) return;
    add.mutate(body, { onSuccess: () => setDraft("") });
  };

  return (
    <section className="mt-7">
      <h3 className="mb-2 text-[13px] font-semibold">Activity</h3>
      <ol className="relative ml-[7px] border-l border-line pl-5">
        {entries.map((e) =>
          e.comment ? (
            <CommentItem key={`c${e.comment.id}`} comment={e.comment} taskId={task.id} />
          ) : e.activity ? (
            <li key={`a${e.activity.id}`} className="relative py-1.5 text-[12.5px] text-ink2">
              <span className="absolute -left-[24.5px] top-[11px] h-2 w-2 rounded-full border border-line2 bg-panel" />
              {describeActivity(e.activity, lookups)}
              <span
                className="ml-2 text-ink3"
                title={new Date(e.activity.created_at).toLocaleString()}
              >
                {formatRelative(e.activity.created_at)}
              </span>
            </li>
          ) : null,
        )}
      </ol>
      <div className="mt-3 rounded-md border border-line focus-within:border-line2">
        <textarea
          value={draft}
          rows={2}
          aria-label="Comment"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Leave a comment"
          className="block w-full resize-none bg-transparent px-3 py-2 text-[13px] outline-none"
        />
        <div className="flex items-center justify-end gap-2 px-2 pb-2">
          <span className="hidden text-[11.5px] text-ink3 desk:inline">
            {keyLabels("mod+enter").join(" ")}
          </span>
          <button
            type="button"
            onClick={submit}
            disabled={!draft.trim() || add.isPending}
            className="h-7 rounded-md bg-accent px-3 text-[12.5px] font-medium text-white disabled:opacity-40 dark:text-bg"
          >
            Comment
          </button>
        </div>
      </div>
    </section>
  );
}

function CommentItem({ comment, taskId }: { comment: Comment; taskId: string }) {
  const { edit, remove } = useCommentMutations(taskId);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(comment.body);
  const edited = comment.updated_at !== comment.created_at;
  return (
    <li className="group relative my-2 rounded-md border border-line bg-bg/40 px-3 py-2">
      <span className="absolute -left-[24.5px] top-[14px] h-2 w-2 rounded-full bg-accent" />
      <div className="mb-1 flex items-center gap-2 text-[12px] text-ink3">
        <span className="font-medium text-ink2">Comment</span>
        <span title={new Date(comment.created_at).toLocaleString()}>
          {formatRelative(comment.created_at)}
        </span>
        {edited && <span>(edited)</span>}
        <span className="flex-1" />
        {!editing && (
          <span className="flex gap-2 opacity-100 desk:opacity-0 desk:group-hover:opacity-100">
            <button type="button" className="hover:text-ink" onClick={() => setEditing(true)}>
              Edit
            </button>
            <button
              type="button"
              className="hover:text-red"
              onClick={() =>
                useUI.getState().setConfirm({
                  title: "Delete this comment?",
                  confirmLabel: "Delete",
                  onConfirm: () => remove.mutate(comment.id),
                })
              }
            >
              Delete
            </button>
          </span>
        )}
      </div>
      {editing ? (
        <div>
          <textarea
            // biome-ignore lint/a11y/noAutofocus: opened by Edit
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.stopPropagation();
                setEditing(false);
                setValue(comment.body);
              } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && value.trim()) {
                edit.mutate({ id: comment.id, body: value.trim() });
                setEditing(false);
              }
            }}
            rows={3}
            className="w-full resize-none rounded border border-line2 p-2 text-[13px] outline-none"
          />
          <div className="mt-1 flex justify-end gap-2 text-[12.5px]">
            <button type="button" className="text-ink3" onClick={() => setEditing(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="font-medium text-accent"
              disabled={!value.trim()}
              onClick={() => {
                edit.mutate({ id: comment.id, body: value.trim() });
                setEditing(false);
              }}
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <div className="md text-[13px]">
          <Md>{comment.body}</Md>
        </div>
      )}
    </li>
  );
}
