import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouterState } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { type AppliedEvent, plain, sendMessage } from "../lib/agentStream";
import { type AgentMessage, type PendingChange, api } from "../lib/api";
import { formatShort } from "../lib/dates";
import {
  qk,
  refreshAfterAgent,
  rememberPending,
  useAgentSettings,
  useLookups,
  usePendingActions,
  usePendingChanges,
  useToday,
} from "../lib/queries";
import { useUI } from "../stores/ui";

const TOOL_LABELS: Record<string, string> = {
  get_overview: "Read overview",
  find_tasks: "Searched tasks",
  get_task: "Read a task",
  list_pending_changes: "Read pending changes",
  save_tasks: "Saved tasks",
  complete_task: "Completed a task",
  reopen_task: "Reopened a task",
  delete_task: "Drafted a delete",
  add_comment: "Commented",
  save_project: "Saved a project",
  save_area: "Saved an area",
  save_label: "Saved a label",
  import_tasks: "Imported tasks",
};

interface ToolLine {
  name: string;
  status: "started" | "done" | "failed";
}

/** One exchange in the panel: the owner's message and the streamed reply. */
interface Exchange {
  key: string;
  owner: { content: string; images: string[]; imageCount: number };
  tools: ToolLine[];
  text: string;
  pendingIds: string[];
  applied: AppliedEvent[];
  error?: string;
  streaming: boolean;
}

function fromHistory(messages: AgentMessage[]): Exchange[] {
  const out: Exchange[] = [];
  for (const m of messages) {
    if (m.role === "owner") {
      out.push({
        key: m.id,
        owner: { content: m.content, images: [], imageCount: m.image_count },
        tools: [],
        text: "",
        pendingIds: [],
        applied: [],
        streaming: false,
      });
    } else if (out.length) {
      const last = out[out.length - 1];
      last.text = m.content;
      last.pendingIds = m.pending_change_ids;
    }
  }
  return out;
}

function screenName(path: string): string {
  if (path.startsWith("/projects/")) return "a project";
  if (path.startsWith("/areas/")) return "an area";
  const name = path.replace(/^\//, "").split("/")[0];
  return name ? name[0].toUpperCase() + name.slice(1) : "Today";
}

const SUGGESTIONS = [
  "What's overdue, and what should I push to the weekend?",
  "Triage my Inbox into projects",
  "Turn this screenshot into tasks",
  "Import this Todoist export",
];

function IconSpark({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 3l1.8 4.9L19 9.7l-4.6 2.6L13 17.5l-2.4-4.6L6 11.4l4.6-1.9z" />
      <path d="M19 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
    </svg>
  );
}
export { IconSpark };

export function Assistant({ phone }: { phone: boolean }) {
  const qc = useQueryClient();
  const settings = useAgentSettings().data;
  const history = useQuery({
    queryKey: qk.conversation,
    queryFn: api.conversation,
    enabled: Boolean(settings?.enabled),
  });
  const pending = usePendingChanges().data ?? [];
  const byId = useMemo(() => new Map(pending.map((p) => [p.id, p])), [pending]);
  const [live, setLive] = useState<Exchange[] | null>(null);
  const [draft, setDraft] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const path = useRouterState({ select: (s) => s.location.pathname });
  const body = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const exchanges = live ?? fromHistory(history.data ?? []);
  const busy = exchanges.some((e) => e.streaming);
  const mode = settings?.mode ?? "suggest";

  useEffect(() => {
    input.current?.focus();
  }, []);
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll on every update
  useEffect(() => {
    body.current?.scrollTo({ top: body.current.scrollHeight });
  }, [exchanges]);

  const update = (key: string, fn: (e: Exchange) => Exchange) =>
    setLive((xs) => (xs ?? []).map((e) => (e.key === key ? fn(e) : e)));

  const send = async (text: string) => {
    if (busy || (!text.trim() && images.length === 0)) return;
    const key = `live-${Date.now()}`;
    const files = images;
    const ex: Exchange = {
      key,
      owner: {
        content: text.trim(),
        images: files.map((f) => URL.createObjectURL(f)),
        imageCount: files.length,
      },
      tools: [],
      text: "",
      pendingIds: [],
      applied: [],
      streaming: true,
    };
    setLive([...exchanges, ex]);
    setDraft("");
    setImages([]);
    try {
      await sendMessage({ content: text, images: files, screen: screenName(path) }, (ev) => {
        if (ev.type === "delta") update(key, (e) => ({ ...e, text: e.text + ev.text }));
        else if (ev.type === "tool")
          update(key, (e) => {
            const tools = [...e.tools];
            let at = -1;
            tools.forEach((t, i) => {
              if (t.name === ev.name && t.status === "started") at = i;
            });
            if (ev.status === "started") tools.push({ name: ev.name, status: "started" });
            else if (at >= 0) tools[at] = { name: ev.name, status: ev.status };
            return { ...e, tools };
          });
        else if (ev.type === "pending_change") {
          rememberPending(qc, ev.change);
          update(key, (e) => ({ ...e, pendingIds: [...e.pendingIds, ev.change.id] }));
        } else if (ev.type === "applied") {
          refreshAfterAgent(qc);
          update(key, (e) => ({ ...e, applied: [...e.applied, ev.applied] }));
        } else if (ev.type === "error") update(key, (e) => ({ ...e, error: ev.message }));
      });
    } catch (err) {
      update(key, (e) => ({ ...e, error: err instanceof Error ? err.message : String(err) }));
    } finally {
      update(key, (e) => ({ ...e, streaming: false }));
      qc.invalidateQueries({ queryKey: qk.pending });
    }
  };

  const addFiles = (files: FileList | File[]) => {
    const ok = [...files].filter((f) => /^image\/(png|jpeg|webp)$/.test(f.type));
    setImages((xs) => [...xs, ...ok].slice(0, 4));
  };

  const clear = async () => {
    await api.clearConversation();
    setLive([]);
    qc.setQueryData(qk.conversation, []);
  };

  const close = () => useUI.getState().setAssistant(false);

  return (
    <aside
      aria-label="Assistant"
      className={
        phone
          ? "anim-sheet fixed inset-0 z-40 flex flex-col bg-panel"
          : "anim-pane relative flex w-[400px] shrink-0 flex-col border-l border-line bg-panel"
      }
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDrag(true);
        }
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        addFiles(e.dataTransfer.files);
      }}
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line pl-4 pr-2">
        <span className="flex items-center gap-1.5 font-semibold text-ink">
          <span className="text-accent">
            <IconSpark />
          </span>
          Assistant
        </span>
        <span
          className="chip !rounded-full"
          title="Agent mode. Change it in Settings."
          data-testid="agent-mode"
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${mode === "apply" ? "bg-accent" : "bg-amber"}`}
          />
          {mode === "apply" ? "Apply" : "Suggest"}
        </span>
        <span className="flex-1" />
        {settings?.enabled && (
          <button
            type="button"
            onClick={clear}
            disabled={busy}
            title="Clear conversation"
            aria-label="Clear conversation"
            className="rounded-md p-1.5 text-ink3 hover:bg-hover hover:text-ink"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              aria-hidden
            >
              <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />
            </svg>
          </button>
        )}
        <button
          type="button"
          onClick={close}
          title="Close (Ctrl J)"
          aria-label="Close assistant"
          className="rounded-md p-1.5 text-ink3 hover:bg-hover hover:text-ink"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </header>

      {settings && !settings.enabled ? (
        <TurnOn />
      ) : (
        <div ref={body} className="scroll-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          {exchanges.length === 0 && (
            <div className="m-auto max-w-[300px] text-center text-ink2">
              <h3 className="mb-1 text-[15px] font-semibold text-ink">Ask Slate</h3>
              <p className="text-[12px] leading-relaxed text-ink3">
                Reads and changes your tasks.{" "}
                {mode === "apply" ? (
                  <>
                    In <b>Apply</b> mode changes happen at once; deletes still ask.
                  </>
                ) : (
                  <>
                    In <b>Suggest</b> mode every change waits for you to apply it.
                  </>
                )}
              </p>
              <div className="mt-4 flex flex-col gap-1.5 text-left">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setDraft(s);
                      input.current?.focus();
                    }}
                    className="rounded-lg border border-line bg-raise px-3 py-2 text-[13px] text-ink2 hover:border-line2 hover:bg-hover hover:text-ink"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {exchanges.map((e) => (
            <ExchangeView key={e.key} e={e} byId={byId} />
          ))}
        </div>
      )}

      {drag && (
        <div className="pointer-events-none absolute inset-3 flex items-center justify-center rounded-xl border-2 border-dashed border-accent/60 bg-accent/5 text-[13px] text-accent">
          Drop images to attach
        </div>
      )}

      {settings?.enabled && (
        <form
          className="shrink-0 border-t border-line px-3 pb-3 pt-2.5"
          onSubmit={(ev) => {
            ev.preventDefault();
            send(draft);
          }}
        >
          <div className="mb-2 flex items-center gap-2 text-[11.5px] text-ink3">
            <span className="chip">On: {screenName(path)}</span>
            <span className="flex-1" />
            <span>
              {mode === "apply"
                ? "Apply mode · changes happen now; deletes still ask"
                : "Suggest mode · nothing changes until you apply"}
            </span>
          </div>
          <div className="rounded-[10px] border border-line2 bg-raise px-2.5 pb-1.5 pt-2 focus-within:border-accent/60">
            {images.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {images.map((f, i) => (
                  <span key={`${f.name}-${i}`} className="chip">
                    {f.name.slice(0, 24)}
                    <button
                      type="button"
                      aria-label={`Remove ${f.name}`}
                      onClick={() => setImages((xs) => xs.filter((_, j) => j !== i))}
                      className="text-ink3 hover:text-ink"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              ref={input}
              aria-label="Message the assistant"
              value={draft}
              rows={2}
              placeholder="Ask, or paste a screenshot…"
              onChange={(e) => setDraft(e.target.value)}
              onPaste={(e) => {
                if (e.clipboardData.files.length) {
                  e.preventDefault();
                  addFiles(e.clipboardData.files);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(draft);
                }
                if (e.key === "Escape") close();
              }}
              className="max-h-48 min-h-[40px] w-full resize-none border-0 text-[13.5px] text-ink outline-none"
            />
            <div className="flex items-center gap-2">
              <label
                className="cursor-pointer rounded-md p-1 text-ink3 hover:bg-hover hover:text-ink"
                title="Attach images (up to 4)"
              >
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  className="sr-only"
                  aria-label="Attach images"
                  onChange={(e) => {
                    if (e.target.files) addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <circle cx="9" cy="10" r="1.6" />
                  <path d="M21 16l-5-5-9 9" />
                </svg>
              </label>
              <span className="text-[11px] text-ink3">
                Enter to send · Shift Enter for a new line
              </span>
              <span className="flex-1" />
              <button
                type="submit"
                aria-label="Send"
                disabled={busy || (!draft.trim() && images.length === 0)}
                className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-accent text-white disabled:opacity-40 dark:text-bg"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            </div>
          </div>
        </form>
      )}
    </aside>
  );
}

function TurnOn() {
  return (
    <div className="m-auto max-w-[300px] p-6 text-center text-[13px] text-ink2">
      <h3 className="mb-1 text-[15px] font-semibold text-ink">The assistant is off</h3>
      <p className="text-ink3">
        Turn it on in Settings. Messages and task text go to the model provider shown there.
      </p>
      <a href="/settings" className="mt-3 inline-block text-accent hover:underline">
        Open Settings
      </a>
    </div>
  );
}

function ExchangeView({ e, byId }: { e: Exchange; byId: Map<string, PendingChange> }) {
  const cards = e.pendingIds.map((id) => byId.get(id)).filter(Boolean) as PendingChange[];
  const pendingLeft = cards.filter((c) => c.status === "pending");
  const { apply, dismiss } = usePendingActions();
  return (
    <div className="flex flex-col gap-2.5">
      <div className="self-end max-w-[86%] rounded-[12px_12px_4px_12px] bg-hover px-3 py-2 text-[13.5px] leading-snug text-ink">
        {e.owner.images.length > 0 && (
          <div className="mb-1.5 flex flex-wrap justify-end gap-1.5">
            {e.owner.images.map((src) => (
              <img
                key={src}
                src={src}
                alt="Attached"
                className="h-[84px] max-w-[150px] rounded-md border border-line2 object-cover"
              />
            ))}
          </div>
        )}
        {e.owner.images.length === 0 && e.owner.imageCount > 0 && (
          <div className="mb-1 text-[11.5px] text-ink3">
            {e.owner.imageCount} image{e.owner.imageCount > 1 ? "s" : ""} (not kept)
          </div>
        )}
        <div className="whitespace-pre-wrap break-words">
          {e.owner.content.length > 600 ? `${e.owner.content.slice(0, 600)}…` : e.owner.content}
        </div>
      </div>
      {e.tools.length > 0 && (
        <div className="flex flex-col gap-0.5 text-[11.5px] text-ink3" data-testid="tool-lines">
          {e.tools.map((t, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: tool lines only append
            <div key={i} className="flex items-center gap-1.5">
              <span
                className={
                  t.status === "done" ? "text-accent" : t.status === "failed" ? "text-red" : ""
                }
              >
                {t.status === "done" ? "✓" : t.status === "failed" ? "↻" : "…"}
              </span>
              {TOOL_LABELS[t.name] ?? t.name}
              {t.status === "failed" && " (retrying)"}
            </div>
          ))}
        </div>
      )}
      {(e.text || e.streaming) && (
        <div className="md text-[13.5px]">
          {e.text ? (
            <ReactMarkdown skipHtml disallowedElements={["img", "a"]} unwrapDisallowed>
              {e.text}
            </ReactMarkdown>
          ) : (
            <span className="text-ink3">Thinking…</span>
          )}
        </div>
      )}
      {e.error && (
        <div className="rounded-md border border-red/40 px-3 py-2 text-[12.5px] text-red">
          {e.error}
        </div>
      )}
      {e.applied.map((a, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: applied events only append
        <AppliedCard key={i} a={a} />
      ))}
      {cards.map((c) => (
        <PendingCard key={c.id} change={c} />
      ))}
      {pendingLeft.length > 1 && (
        <div className="flex items-center gap-2 text-[12px] text-ink2">
          <span>{pendingLeft.length} pending</span>
          <span className="flex-1" />
          <button
            type="button"
            className={btn}
            onClick={() => {
              for (const c of pendingLeft) dismiss.mutate(c.id);
            }}
          >
            Dismiss all
          </button>
          <button
            type="button"
            className={btnPrimary}
            onClick={() => {
              for (const c of pendingLeft) apply.mutate({ id: c.id, input: applyInput(c) });
            }}
          >
            Apply all {pendingLeft.length}
          </button>
        </div>
      )}
    </div>
  );
}

const btn =
  "h-[26px] rounded-md border border-line2 bg-panel px-2.5 text-[12px] font-medium text-ink2 hover:bg-hover hover:text-ink disabled:opacity-50";
const btnPrimary =
  "h-[26px] rounded-md border border-accent bg-accent px-2.5 text-[12px] font-medium text-white hover:brightness-110 disabled:opacity-50 dark:text-bg";

const APPLIED_LABELS: Record<string, string> = {
  save_tasks: "Saved",
  complete_task: "Completed",
  reopen_task: "Reopened",
  add_comment: "Commented",
  save_project: "Project",
  save_area: "Area",
  save_label: "Label",
  import_tasks: "Imported",
};

function AppliedCard({ a }: { a: AppliedEvent }) {
  return (
    <div className="rounded-lg border border-l-[3px] border-line border-l-accent bg-raise px-3 py-2">
      <div className="flex items-center text-[11px] uppercase tracking-wide text-ink3">
        {APPLIED_LABELS[a.tool] ?? a.tool.replace(/_/g, " ")}
        <span className="ml-auto normal-case tracking-normal text-accent">✓ Applied</span>
      </div>
      <div className="mt-1 text-[13px] text-ink">{a.summary}</div>
      {a.tasks.slice(0, 5).map((t) => (
        <button
          type="button"
          key={String(t.id)}
          onClick={() => useUI.getState().openDetail(String(t.id))}
          className="mt-1 flex w-full items-center gap-2 text-left text-[12.5px] text-ink2 hover:text-ink"
        >
          <span className="text-ink3">{String(t.key)}</span>
          <span className="truncate">{plain(t.title)}</span>
        </button>
      ))}
    </div>
  );
}

type TaskDraft = {
  ref?: string;
  title?: string;
  project_id?: string | null;
  due_date?: string | null;
  priority?: number;
  source_text?: string;
};

/** Card edits by Pending change id, so "Apply all" applies what the owner sees. */
const cardEdits = new Map<string, Record<string, unknown>>();

export function applyInput(change: PendingChange): Record<string, unknown> | undefined {
  return cardEdits.get(change.id);
}

const PRIORITY = ["No priority", "P1 Urgent", "P2 High", "P3 Medium", "P4 Low"];

/** One Pending change. save_tasks drafts with one task get editable fields. */
export function PendingCard({ change }: { change: PendingChange }) {
  const { apply, dismiss } = usePendingActions();
  const lookups = useLookups();
  const today = useToday();
  const single =
    change.tool === "save_tasks" &&
    Array.isArray(change.input.tasks) &&
    (change.input.tasks as unknown[]).length === 1;
  const original = single ? ((change.input.tasks as TaskDraft[])[0] ?? {}) : null;
  const [edit, setEditState] = useState<TaskDraft | null>(original);
  const setEdit = (next: TaskDraft) => {
    setEditState(next);
    cardEdits.set(change.id, { tasks: [{ ...original, ...next }] });
  };
  const isDelete = change.tool === "delete_task";
  const status = change.status;
  const border =
    status === "applied"
      ? "border-l-accent"
      : status === "pending"
        ? isDelete
          ? "border-l-red"
          : "border-l-amber"
        : "border-l-line2";
  const label = isDelete
    ? "Delete"
    : change.tool === "save_tasks"
      ? original?.ref
        ? "Update task"
        : "New task"
      : change.tool.replace(/_/g, " ");
  const busy = apply.isPending || dismiss.isPending;
  const projects = [...lookups.projects.values()].filter(
    (p) => p.status !== "done" && p.status !== "canceled",
  );

  const doApply = () => apply.mutate({ id: change.id, input: applyInput(change) });

  return (
    <div
      className={`overflow-hidden rounded-lg border border-l-[3px] border-line bg-raise ${border}`}
      data-testid="pending-card"
    >
      <div className="flex items-center px-3 pt-2 text-[11px] uppercase tracking-wide text-ink3">
        {label}
        {change.origin === "mcp" && <span className="ml-1.5 normal-case">· from MCP</span>}
        <span
          className={`ml-auto text-[11.5px] normal-case tracking-normal ${
            status === "applied" ? "text-accent" : status === "pending" ? "text-amber" : "text-ink3"
          }`}
        >
          {status === "applied"
            ? "✓ Applied"
            : status === "dismissed"
              ? "Dismissed"
              : isDelete
                ? "Needs your OK"
                : "Pending"}
        </span>
      </div>
      <div className="px-3 pb-2 pt-1">
        {single && edit && status === "pending" ? (
          <>
            <div className="flex items-center gap-2">
              <span className="h-3.5 w-3.5 shrink-0 rounded-full border-[1.5px] border-ink3" />
              <input
                aria-label="Title"
                value={edit.title ?? ""}
                placeholder={original?.ref ? "(unchanged title)" : "Title"}
                onChange={(e) => setEdit({ ...edit, title: e.target.value })}
                className="flex-1 border-0 border-b border-dashed border-transparent text-[13.5px] font-medium text-ink outline-none hover:border-line2 focus:border-line2"
              />
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5 pl-[22px]">
              <select
                aria-label="Project"
                value={edit.project_id ?? ""}
                onChange={(e) => setEdit({ ...edit, project_id: e.target.value || null })}
                className="chip cursor-pointer bg-panel outline-none"
              >
                <option value="">No project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <label className="chip cursor-pointer bg-panel">
                <input
                  type="date"
                  aria-label="Due date"
                  value={edit.due_date ?? ""}
                  onChange={(e) => setEdit({ ...edit, due_date: e.target.value || null })}
                  className="w-[112px] border-0 bg-transparent text-[11.5px] outline-none"
                />
              </label>
              <select
                aria-label="Priority"
                value={edit.priority ?? 0}
                onChange={(e) => setEdit({ ...edit, priority: Number(e.target.value) })}
                className="chip cursor-pointer bg-panel outline-none"
              >
                {PRIORITY.map((p, i) => (
                  <option key={p} value={i}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            {edit.source_text && (
              <div className="mt-1.5 pl-[22px] text-[11.5px] italic text-ink3">
                From: “{edit.source_text}”
              </div>
            )}
          </>
        ) : (
          <div className="text-[13px] text-ink">
            {change.summary}
            {single && Boolean(original?.due_date) && status !== "pending" && (
              <span className="text-ink3"> · {formatShort(String(original?.due_date), today)}</span>
            )}
          </div>
        )}
        {apply.error ? (
          <div className="mt-1 text-[12px] text-red">{(apply.error as Error).message}</div>
        ) : null}
      </div>
      {status === "pending" && (
        <div className="flex justify-end gap-1.5 px-3 pb-2.5">
          <button
            type="button"
            className={btn}
            disabled={busy}
            onClick={() => dismiss.mutate(change.id)}
          >
            {isDelete ? "Keep" : "Dismiss"}
          </button>
          <button
            type="button"
            className={isDelete ? `${btnPrimary} !border-red !bg-red` : btnPrimary}
            disabled={busy}
            onClick={doApply}
          >
            {isDelete ? "Delete" : "Apply"}
          </button>
        </div>
      )}
    </div>
  );
}
