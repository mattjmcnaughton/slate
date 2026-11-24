import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTaskActions } from "../lib/actions";
import { api } from "../lib/api";
import { keyLabels } from "../lib/keys";
import { useDebounced, useLookups, useToday } from "../lib/queries";
import { useTheme } from "../stores/theme";
import { targetIds, useUI } from "../stores/ui";
import { DueChip } from "./TaskMeta";
import {
  Dot,
  IconAll,
  IconBoard,
  IconCalendar,
  IconCheck,
  IconInbox,
  IconMoon,
  IconPlus,
  IconProjects,
  IconSearch,
  IconSettings,
  IconSignOut,
  IconSun,
  IconTag,
  IconToday,
  IconTrash,
  IconUpcoming,
  PriorityIcon,
  StatusIcon,
} from "./icons";

interface Entry {
  id: string;
  group: string;
  label: string;
  icon: React.ReactNode;
  keys?: string;
  hint?: React.ReactNode;
  run: () => void;
}

/** Subsequence match with a bonus for word starts; null when it does not match. */
function score(query: string, text: string): number | null {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (!q) return 0;
  const idx = t.indexOf(q);
  if (idx >= 0) return idx === 0 || t[idx - 1] === " " ? 100 - idx : 50 - idx;
  let pos = 0;
  for (const ch of q) {
    pos = t.indexOf(ch, pos);
    if (pos === -1) return null;
    pos++;
  }
  return 10;
}

export function signOut() {
  const form = document.createElement("form");
  form.method = "post";
  form.action = "/auth/signout";
  document.body.appendChild(form);
  form.submit();
}

export function Palette() {
  const mode = useUI((s) => s.palette);
  if (!mode) return null;
  return <PaletteDialog key={mode} mode={mode} />;
}

function PaletteDialog({ mode }: { mode: "commands" | "search" }) {
  const navigate = useNavigate();
  const lookups = useLookups();
  const today = useToday();
  const theme = useTheme();
  const actions = useTaskActions();
  const page = useUI((s) => s.page);
  const [query, setQuery] = useState("");
  const [at, setAt] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const close = () => useUI.getState().setPalette(null);
  const debounced = useDebounced(query.trim(), 120);
  const targets = targetIds();

  const search = useQuery({
    queryKey: ["search", debounced],
    queryFn: () =>
      api.tasks({ q: debounced, include_closed: true, sort: "updated", order: "desc", limit: 12 }),
    enabled: debounced.length > 0,
  });

  const go = (to: string) => () => navigate({ to });
  const openMenu = (kind: "status" | "priority" | "due" | "labels" | "project") => () =>
    useUI.getState().openMenu({ kind, taskIds: targets });

  const commands: Entry[] = [];
  if (mode === "commands") {
    if (targets.length) {
      const n = targets.length === 1 ? "task" : `${targets.length} tasks`;
      commands.push(
        {
          id: "complete",
          group: "Selection",
          label: `Complete ${n}`,
          icon: <IconCheck size={14} />,
          keys: "e",
          run: () => actions.toggleComplete(targets),
        },
        {
          id: "status",
          group: "Selection",
          label: "Change status…",
          icon: <StatusIcon status="in_progress" />,
          keys: "s",
          run: openMenu("status"),
        },
        {
          id: "priority",
          group: "Selection",
          label: "Set priority…",
          icon: <PriorityIcon priority={2} />,
          keys: "p",
          run: openMenu("priority"),
        },
        {
          id: "due",
          group: "Selection",
          label: "Set due date…",
          icon: <IconCalendar size={14} />,
          keys: "d",
          run: openMenu("due"),
        },
        {
          id: "labels",
          group: "Selection",
          label: "Edit labels…",
          icon: <IconTag size={14} />,
          keys: "l",
          run: openMenu("labels"),
        },
        {
          id: "move",
          group: "Selection",
          label: "Move to project…",
          icon: <IconProjects size={14} />,
          run: openMenu("project"),
        },
        {
          id: "delete",
          group: "Selection",
          label: `Delete ${n}…`,
          icon: <IconTrash size={14} />,
          keys: "backspace",
          run: () => actions.confirmDelete(targets),
        },
      );
    }
    commands.push(
      {
        id: "new",
        group: "Commands",
        label: "Add a task",
        icon: <IconPlus size={14} />,
        keys: "c",
        run: () => useUI.getState().setQuickAdd(true),
      },
      {
        id: "today",
        group: "Go to",
        label: "Today",
        icon: <IconToday size={14} />,
        keys: "g t",
        run: go("/today"),
      },
      {
        id: "upcoming",
        group: "Go to",
        label: "Upcoming",
        icon: <IconUpcoming size={14} />,
        keys: "g u",
        run: go("/upcoming"),
      },
      {
        id: "inbox",
        group: "Go to",
        label: "Inbox",
        icon: <IconInbox size={14} />,
        keys: "g i",
        run: go("/inbox"),
      },
      {
        id: "all",
        group: "Go to",
        label: "All tasks",
        icon: <IconAll size={14} />,
        keys: "g a",
        run: go("/all"),
      },
      {
        id: "projects",
        group: "Go to",
        label: "Projects",
        icon: <IconProjects size={14} />,
        keys: "g p",
        run: go("/projects"),
      },
      {
        id: "settings",
        group: "Go to",
        label: "Settings",
        icon: <IconSettings size={14} />,
        run: go("/settings"),
      },
    );
    if (page.toggleView) {
      commands.push({
        id: "view",
        group: "Commands",
        label: "Switch list / board",
        icon: <IconBoard size={14} />,
        keys: "v",
        run: page.toggleView,
      });
    }
    commands.push(
      {
        id: "theme",
        group: "Commands",
        label: theme.theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        icon: theme.theme === "dark" ? <IconSun size={14} /> : <IconMoon size={14} />,
        run: theme.toggle,
      },
      {
        id: "keys",
        group: "Commands",
        label: "Keyboard shortcuts",
        icon: <span className="text-[12px]">?</span>,
        keys: "?",
        run: () => useUI.getState().setShortcuts(true),
      },
      {
        id: "signout",
        group: "Commands",
        label: "Sign out",
        icon: <IconSignOut size={14} />,
        run: signOut,
      },
    );
  }

  const projectEntries: Entry[] = [...lookups.projects.values()].map((p) => {
    const area = p.area_id ? lookups.areas.get(p.area_id) : undefined;
    return {
      id: `p${p.id}`,
      group: "Projects",
      label: p.name,
      icon: <Dot color={p.color ?? area?.color ?? "rgb(var(--ink3))"} />,
      hint: area?.name,
      run: () => navigate({ to: "/projects/$projectId", params: { projectId: p.id } }),
    };
  });

  const q = query.trim();
  const ranked = (list: Entry[]) =>
    list
      .map((e) => ({ e, s: score(q, `${e.label} ${typeof e.hint === "string" ? e.hint : ""}`) }))
      .filter((x) => x.s !== null)
      .sort((a, b) => (b.s ?? 0) - (a.s ?? 0))
      .map((x) => x.e);

  const taskEntries: Entry[] =
    q && search.data
      ? search.data.map((t) => ({
          id: `t${t.id}`,
          group: "Tasks",
          label: t.title,
          icon: <StatusIcon status={t.status} />,
          hint: (
            <span className="flex items-center gap-2">
              <DueChip task={t} today={today} />
              <span className="tabular-nums">{t.key}</span>
            </span>
          ),
          run: () => useUI.getState().openDetail(t.id),
        }))
      : [];

  const entries =
    mode === "search"
      ? [...taskEntries, ...(q ? ranked(projectEntries).slice(0, 5) : [])]
      : q
        ? [...ranked(commands), ...ranked(projectEntries).slice(0, 5), ...taskEntries]
        : commands;

  // biome-ignore lint/correctness/useExhaustiveDependencies: reset the cursor when results change
  useEffect(() => setAt(0), [query, search.data]);
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  });

  const run = (e: Entry | undefined) => {
    if (!e) return;
    close();
    e.run();
  };

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex justify-center bg-ink/20 px-3 pt-[12vh] desk:pt-[14vh]">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 cursor-default"
        onClick={close}
      />
      <div
        role="dialog"
        aria-label={mode === "search" ? "Search" : "Command palette"}
        className="popover anim-rise relative flex h-fit max-h-[64vh] w-full max-w-[620px] flex-col overflow-hidden"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <IconSearch className="text-ink3" />
          <input
            // biome-ignore lint/a11y/noAutofocus: the palette opens to type
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || (e.ctrlKey && e.key === "n")) {
                e.preventDefault();
                setAt((a) => Math.min(entries.length - 1, a + 1));
              } else if (e.key === "ArrowUp" || (e.ctrlKey && e.key === "p")) {
                e.preventDefault();
                setAt((a) => Math.max(0, a - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(entries[at]);
              }
            }}
            placeholder={
              mode === "search" ? "Search tasks and projects" : "Type a command or search"
            }
            className="h-12 flex-1 text-[15px] outline-none"
          />
          <kbd className="kbd">Esc</kbd>
        </div>
        <div
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          className="scroll-thin overflow-y-auto py-1.5"
        >
          {entries.length === 0 && (
            <div className="px-4 py-6 text-center text-[13px] text-ink3">
              {q
                ? search.isFetching
                  ? "Searching…"
                  : `Nothing matches “${q}”`
                : "Type to search tasks by title"}
            </div>
          )}
          {entries.map((e, i) => {
            const header = e.group !== lastGroup ? e.group : null;
            lastGroup = e.group;
            return (
              <div key={e.id}>
                {header && (
                  <div className="px-4 pb-1 pt-2 text-[11.5px] font-medium text-ink3">{header}</div>
                )}
                <div
                  role="option"
                  tabIndex={-1}
                  aria-selected={i === at}
                  onMouseMove={() => i !== at && setAt(i)}
                  onClick={() => run(e)}
                  onKeyDown={() => {}}
                  className={`mx-1.5 flex h-9 cursor-default items-center gap-3 rounded-md px-2.5 text-[13.5px] ${
                    i === at ? "bg-hover text-ink" : "text-ink2"
                  }`}
                >
                  <span className="flex w-4 justify-center">{e.icon}</span>
                  <span className="min-w-0 flex-1 truncate">{e.label}</span>
                  {e.hint && <span className="shrink-0 text-[12px] text-ink3">{e.hint}</span>}
                  {e.keys && (
                    <span className="flex shrink-0 gap-1">
                      {keyLabels(e.keys).map((k, j) => (
                        // biome-ignore lint/suspicious/noArrayIndexKey: static key chips
                        <kbd key={j} className="kbd">
                          {k}
                        </kbd>
                      ))}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
