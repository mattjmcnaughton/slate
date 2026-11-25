import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useMemo } from "react";
import { useIsPhone } from "../hooks/useMedia";
import { useTaskActions } from "../lib/actions";
import { type Binding, createDispatcher } from "../lib/keys";
import {
  findTask,
  useAgenda,
  useAreas,
  useMe,
  usePendingChanges,
  useProjects,
  useTasks,
} from "../lib/queries";
import { useTheme } from "../stores/theme";
import { anyLayerOpen, targetIds, useUI } from "../stores/ui";
import { Assistant, IconSpark } from "./Assistant";
import { MenuHost } from "./Menus";
import { ConfirmDialog, Keys, ShortcutSheet, Toasts } from "./Overlays";
import { Palette, signOut } from "./Palette";
import { QuickAddModal } from "./QuickAdd";
import { TaskDetail } from "./TaskDetail";
import {
  Dot,
  IconAll,
  IconInbox,
  IconMoon,
  IconPlus,
  IconProjects,
  IconSearch,
  IconSettings,
  IconSignOut,
  IconSun,
  IconToday,
  IconUpcoming,
} from "./icons";

function useGlobalKeys() {
  const navigate = useNavigate();
  const actions = useTaskActions();
  const actionsRef = useMemo(() => ({ current: actions }), [actions]);
  actionsRef.current = actions;

  useEffect(() => {
    const ui = () => useUI.getState();
    const free = () => !anyLayerOpen();
    const hasTarget = () => free() && targetIds().length > 0;
    const menu = (kind: "status" | "priority" | "labels" | "due" | "project") => () =>
      ui().openMenu({ kind, taskIds: targetIds() });
    const go = (to: string) => () => {
      ui().closeDetail();
      navigate({ to });
    };

    const bindings: Binding[] = [
      {
        keys: "mod+j",
        allowInInput: true,
        run: () => ui().setAssistant(!ui().assistant),
      },
      {
        keys: "mod+k",
        allowInInput: true,
        run: () => ui().setPalette(ui().palette ? null : "commands"),
      },
      { keys: "escape", allowInInput: true, run: closeTop, when: () => hasLayer() },
      {
        keys: "c",
        when: free,
        run: () => {
          const inline = ui().inlineQuickAdd;
          if (inline && !ui().detailId) inline();
          else ui().setQuickAdd(true);
        },
      },
      { keys: "/", when: free, run: () => ui().setPalette("search") },
      { keys: "?", when: free, run: () => ui().setShortcuts(true) },
      { keys: "g t", when: free, run: go("/today") },
      { keys: "g u", when: free, run: go("/upcoming") },
      { keys: "g i", when: free, run: go("/inbox") },
      { keys: "g a", when: free, run: go("/all") },
      { keys: "g p", when: free, run: go("/projects") },
      { keys: "j", when: free, run: () => ui().move(1) },
      { keys: "k", when: free, run: () => ui().move(-1) },
      { keys: "arrowdown", when: free, run: () => ui().move(1) },
      { keys: "arrowup", when: free, run: () => ui().move(-1) },
      {
        keys: "enter",
        when: () => free() && ui().selectedId !== null,
        run: () => ui().openDetail(ui().selectedId as string),
      },
      {
        keys: "x",
        when: () => free() && ui().selectedId !== null,
        run: () => ui().toggleChecked(ui().selectedId as string),
      },
      { keys: "e", when: hasTarget, run: () => actionsRef.current.toggleComplete(targetIds()) },
      { keys: "s", when: hasTarget, run: menu("status") },
      { keys: "p", when: hasTarget, run: menu("priority") },
      { keys: "d", when: hasTarget, run: menu("due") },
      { keys: "l", when: hasTarget, run: menu("labels") },
      { keys: "m", when: hasTarget, run: menu("project") },
      {
        keys: "backspace",
        when: hasTarget,
        run: () => actionsRef.current.confirmDelete(targetIds()),
      },
      { keys: "delete", when: hasTarget, run: () => actionsRef.current.confirmDelete(targetIds()) },
      {
        keys: "v",
        when: () => free() && Boolean(ui().page.toggleView),
        run: () => ui().page.toggleView?.(),
      },
    ];

    const dispatch = createDispatcher(() => bindings);
    const onKey = (e: KeyboardEvent) => {
      dispatch(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, actionsRef]);
}

function hasLayer() {
  const s = useUI.getState();
  return anyLayerOpen() || s.detailId !== null || s.checkedIds.length > 0;
}

/** Esc closes the top layer only. */
function closeTop() {
  const s = useUI.getState();
  if (s.confirm) s.setConfirm(null);
  else if (s.menu) s.closeMenu();
  else if (s.palette) s.setPalette(null);
  else if (s.quickAdd) s.setQuickAdd(false);
  else if (s.shortcuts) s.setShortcuts(false);
  else if (s.detailId !== null) s.closeDetail();
  else if (s.checkedIds.length) s.clearChecked();
}

export function Shell({ children }: { children: React.ReactNode }) {
  const phone = useIsPhone();
  const detailId = useUI((s) => s.detailId);
  const assistant = useUI((s) => s.assistant);
  const me = useMe();
  useGlobalKeys();

  // Close the detail when the route changes.
  const path = useRouterState({ select: (s) => s.location.pathname });
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs on each route change
  useEffect(() => {
    useUI.getState().closeDetail();
    useUI.getState().clearChecked();
    useUI.getState().select(null);
  }, [path]);

  if (me.isLoading) return <div className="h-full bg-bg" />;
  if (me.isError) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-[14px] text-ink2">
        <div>
          <p>Slate could not reach the server.</p>
          <button type="button" className="mt-3 text-accent underline" onClick={() => me.refetch()}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {!phone && <Sidebar />}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1">
          <main className="scroll-thin min-w-0 flex-1 overflow-y-auto pb-[calc(64px+env(safe-area-inset-bottom))] desk:pb-0">
            {children}
          </main>
          {detailId !== null && <TaskDetail id={detailId} phone={phone} />}
          {assistant && !phone && <Assistant phone={false} />}
        </div>
        {!phone && <ModeLine />}
      </div>
      {phone && <TabBar />}
      {assistant && phone && <Assistant phone />}
      {phone && !assistant && detailId === null && (
        <button
          type="button"
          aria-label="Open assistant"
          onClick={() => useUI.getState().setAssistant(true)}
          className="fixed bottom-[calc(144px+env(safe-area-inset-bottom))] right-5 z-30 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-raise text-accent shadow-[var(--shadow)]"
        >
          <IconSpark size={20} />
        </button>
      )}
      {phone && detailId === null && (
        <button
          type="button"
          aria-label="Add a task"
          onClick={() => useUI.getState().setQuickAdd(true)}
          className="fixed bottom-[calc(72px+env(safe-area-inset-bottom))] right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-white shadow-[var(--shadow)] dark:text-bg"
        >
          <IconPlus size={24} />
        </button>
      )}
      <QuickAddModal />
      <Palette />
      <MenuHost />
      <ShortcutSheet />
      <ConfirmDialog />
      <Toasts />
    </div>
  );
}

function NavItem({
  to,
  icon,
  label,
  count,
  keys,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  count?: number;
  keys?: string;
}) {
  return (
    <Link
      to={to}
      className="group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] text-ink2 hover:bg-hover hover:text-ink"
      activeProps={{ className: "!bg-accent-soft !text-ink font-medium" }}
      activeOptions={{ exact: false }}
      title={keys ? `${label} (${keys})` : label}
    >
      <span className="text-ink3 group-[.font-medium]:text-accent">{icon}</span>
      <span className="flex-1 truncate">{label}</span>
      {count ? <span className="text-[12px] tabular-nums text-ink3">{count}</span> : null}
    </Link>
  );
}

function Sidebar() {
  const areas = useAreas().data ?? [];
  const projects = useProjects().data ?? [];
  const agenda = useAgenda().data;
  const inbox = useTasks({ inbox: true, top_level: true }).data;
  const pending = (usePendingChanges().data ?? []).filter((p) => p.status === "pending").length;
  const assistantOpen = useUI((s) => s.assistant);
  const theme = useTheme();
  const todayCount = agenda
    ? agenda.overdue.length + (agenda.days.find((d) => d.date === agenda.today)?.tasks.length ?? 0)
    : undefined;
  const live = projects.filter((p) => p.status !== "done" && p.status !== "canceled");

  return (
    <nav aria-label="Main" className="flex w-[232px] shrink-0 flex-col border-r border-line bg-bg">
      <div className="flex h-12 items-center gap-2 px-4">
        <span className="flex h-5 w-5 items-center justify-center rounded-[5px] bg-accent text-white dark:text-bg">
          <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden>
            <path
              d="M2.5 6.3l2.3 2.3L9.6 3.6"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span className="text-[14px] font-semibold tracking-[-0.01em]">Slate</span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => useUI.getState().setPalette("commands")}
          className="flex items-center gap-1 rounded-md px-1.5 py-1 text-ink3 hover:bg-hover hover:text-ink"
          aria-label="Command palette"
          title="Command palette"
        >
          <IconSearch size={14} />
          <Keys keys="mod+k" />
        </button>
      </div>
      <div className="px-2 pb-2">
        <button
          type="button"
          onClick={() => useUI.getState().setQuickAdd(true)}
          className="flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] text-ink2 hover:bg-hover hover:text-ink"
        >
          <IconPlus size={16} className="text-accent" />
          <span className="flex-1 text-left">Add task</span>
          <kbd className="kbd">C</kbd>
        </button>
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto px-2">
        <NavItem to="/today" icon={<IconToday />} label="Today" count={todayCount} keys="g t" />
        <NavItem to="/upcoming" icon={<IconUpcoming />} label="Upcoming" keys="g u" />
        <NavItem to="/inbox" icon={<IconInbox />} label="Inbox" count={inbox?.length} keys="g i" />
        <NavItem to="/all" icon={<IconAll />} label="All tasks" keys="g a" />
        <Link
          to="/pending"
          className="group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] text-ink2 hover:bg-hover hover:text-ink"
          activeProps={{ className: "!bg-accent-soft !text-ink font-medium" }}
        >
          <span className="text-ink3">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              aria-hidden
            >
              <circle cx="12" cy="12" r="8" />
              <path d="M12 8v4l3 2" />
            </svg>
          </span>
          <span className="flex-1 truncate">Pending changes</span>
          {pending > 0 && (
            <span className="rounded-full bg-amber/15 px-1.5 text-[11px] leading-4 tabular-nums text-amber">
              {pending}
            </span>
          )}
        </Link>
        <button
          type="button"
          onClick={() => useUI.getState().setAssistant(!assistantOpen)}
          aria-pressed={assistantOpen}
          className={`flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] hover:bg-hover hover:text-ink ${
            assistantOpen ? "bg-accent-soft font-medium text-ink" : "text-ink2"
          }`}
        >
          <span className="text-accent">
            <IconSpark />
          </span>
          <span className="flex-1 text-left">Assistant</span>
          <Keys keys="mod+j" />
        </button>

        <div className="mb-1 mt-5 flex items-center justify-between px-2.5">
          <Link to="/projects" className="text-[12px] font-medium text-ink3 hover:text-ink">
            Areas and projects
          </Link>
        </div>
        {[...areas, null].map((area) => {
          const own = live.filter((p) => p.area_id === (area?.id ?? null));
          if (!area && !own.length) return null;
          return (
            <div key={area?.id ?? "none"} className="mb-1.5">
              {area ? (
                <Link
                  to="/areas/$areaId"
                  params={{ areaId: area.id }}
                  className="flex h-7 items-center gap-2.5 rounded-md px-2.5 text-[13px] text-ink hover:bg-hover"
                  activeProps={{ className: "!bg-accent-soft font-medium" }}
                >
                  <Dot color={area.color} />
                  <span className="truncate">{area.name}</span>
                </Link>
              ) : (
                <div className="px-2.5 pt-1 text-[12px] text-ink3">No area</div>
              )}
              {own.map((p) => (
                <Link
                  key={p.id}
                  to="/projects/$projectId"
                  params={{ projectId: p.id }}
                  className="flex h-7 items-center gap-2 rounded-md pl-[30px] pr-2.5 text-[13px] text-ink2 hover:bg-hover hover:text-ink"
                  activeProps={{ className: "!bg-accent-soft !text-ink font-medium" }}
                >
                  <span className="flex-1 truncate">{p.name}</span>
                  {p.open_count > 0 && (
                    <span className="text-[11.5px] tabular-nums text-ink3">{p.open_count}</span>
                  )}
                </Link>
              ))}
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-1 border-t border-line px-2 py-2">
        <Link
          to="/settings"
          className="flex h-8 flex-1 items-center gap-2 rounded-md px-2.5 text-[13px] text-ink2 hover:bg-hover hover:text-ink"
          activeProps={{ className: "!bg-accent-soft !text-ink" }}
        >
          <IconSettings size={15} />
          Settings
        </Link>
        <button
          type="button"
          onClick={theme.toggle}
          aria-label={theme.theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme.theme === "dark" ? "Light theme" : "Dark theme"}
          className="rounded-md p-2 text-ink3 hover:bg-hover hover:text-ink"
        >
          {theme.theme === "dark" ? <IconSun size={15} /> : <IconMoon size={15} />}
        </button>
        <button
          type="button"
          onClick={signOut}
          aria-label="Sign out"
          title="Sign out"
          className="rounded-md p-2 text-ink3 hover:bg-hover hover:text-ink"
        >
          <IconSignOut size={15} />
        </button>
      </div>
    </nav>
  );
}

function ModeLine() {
  const selected = useUI((s) => s.selectedId);
  const qc = useQueryClient();
  const selectedKey = selected === null ? undefined : findTask(qc, selected)?.key;
  const checked = useUI((s) => s.checkedIds.length);
  const detail = useUI((s) => s.detailId);
  const view = useUI((s) => Boolean(s.page.toggleView));
  const hint = (keys: string, label: string) => (
    <span key={keys} className="flex items-center gap-1.5 whitespace-nowrap">
      <Keys keys={keys} />
      <span>{label}</span>
    </span>
  );
  const target = checked > 0 || selected !== null;
  return (
    <footer className="flex h-8 shrink-0 items-center gap-4 overflow-hidden border-t border-line bg-bg px-4 text-[11.5px] text-ink3">
      <span className="min-w-[88px] font-medium text-ink2">
        {checked > 0 ? `${checked} selected` : (selectedKey ?? "Slate")}
      </span>
      {target ? (
        <>
          {hint("e", "complete")}
          {hint("s", "status")}
          {hint("p", "priority")}
          {hint("d", "due")}
          {hint("l", "labels")}
          {hint("x", "select")}
          {detail === null ? hint("enter", "open") : hint("escape", "close")}
          {hint("backspace", "delete")}
        </>
      ) : (
        <>
          {hint("j", "next")}
          {hint("k", "previous")}
          {hint("c", "add")}
          {hint("g t", "today")}
        </>
      )}
      <span className="flex-1" />
      {view && hint("v", "list / board")}
      {hint("mod+k", "commands")}
      {hint("?", "shortcuts")}
    </footer>
  );
}

function TabBar() {
  const tabs = [
    { to: "/today", label: "Today", icon: <IconToday size={20} /> },
    { to: "/upcoming", label: "Upcoming", icon: <IconUpcoming size={20} /> },
    { to: "/inbox", label: "Inbox", icon: <IconInbox size={20} /> },
    { to: "/projects", label: "Projects", icon: <IconProjects size={20} /> },
    { to: "/all", label: "All", icon: <IconAll size={20} /> },
  ];
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-panel/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
    >
      {tabs.map((t) => (
        <Link
          key={t.to}
          to={t.to}
          className="flex h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[10.5px] text-ink3"
          activeProps={{ className: "!text-accent font-medium" }}
        >
          {t.icon}
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
