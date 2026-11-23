import {
  type QueryClient,
  type QueryKey,
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useUI } from "../stores/ui";
import {
  type Agenda,
  type Area,
  type Label,
  type Project,
  type QuickAddIn,
  type Task,
  type TaskIn,
  type TaskPatch,
  type TaskQuery,
  api,
} from "./api";
import { addDays, formatShort } from "./dates";

export const qk = {
  me: ["me"] as const,
  settings: ["settings"] as const,
  areas: ["areas"] as const,
  projects: ["projects"] as const,
  labels: ["labels"] as const,
  tasks: (q: TaskQuery) => ["tasks", q] as const,
  task: (id: number) => ["task", id] as const,
  comments: (id: number) => ["comments", id] as const,
  activity: (id: number) => ["activity", id] as const,
  agenda: (days: number) => ["agenda", days] as const,
  parse: (text: string) => ["parse", text] as const,
};

// --- reads ------------------------------------------------------------------------

export const useMe = () =>
  useQuery({ queryKey: qk.me, queryFn: api.me, staleTime: Number.POSITIVE_INFINITY });
export const useSettings = () => useQuery({ queryKey: qk.settings, queryFn: api.settings });
export const useAreas = () =>
  useQuery({
    queryKey: qk.areas,
    queryFn: api.areas,
    select: (areas: Area[]) => [...areas].sort((a, b) => a.position - b.position),
  });
export const useProjects = () =>
  useQuery({
    queryKey: qk.projects,
    queryFn: () => api.projects(),
    select: (ps: Project[]) => [...ps].sort((a, b) => a.position - b.position || a.id - b.id),
  });
export const useLabels = () => useQuery({ queryKey: qk.labels, queryFn: api.labels });

export const useTasks = (q: TaskQuery, enabled = true) =>
  useQuery({
    queryKey: qk.tasks(q),
    queryFn: () => api.tasks(q),
    enabled,
    placeholderData: keepPreviousData,
  });

/** Agenda from today for `days` days (today included). */
export function useAgenda(days = 14) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: qk.agenda(days),
    queryFn: async () => {
      if (days === 14) return api.agenda();
      // The server's default range starts today in the user's zone; reuse it for the start.
      const base = await qc.ensureQueryData({
        queryKey: qk.agenda(14),
        queryFn: () => api.agenda(),
      });
      return api.agenda(base.today, addDays(base.today, days - 1));
    },
    placeholderData: keepPreviousData,
  });
}

/** Today's date in the user's time zone, from the server. */
export function useToday(): string | undefined {
  return useAgenda().data?.today;
}

export function useTask(id: number | null) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: qk.task(id ?? 0),
    queryFn: () => api.task(id as number),
    enabled: id !== null,
    initialData: () => (id === null ? undefined : findTask(qc, id)),
    initialDataUpdatedAt: 0,
  });
}

export const useComments = (id: number) =>
  useQuery({ queryKey: qk.comments(id), queryFn: () => api.comments(id) });
export const useActivity = (id: number) =>
  useQuery({ queryKey: qk.activity(id), queryFn: () => api.activity(id) });

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Live natural-language parse, debounced like typing should be (~120ms). */
export function useParse(text: string) {
  const debounced = useDebounced(text.trim() ? text : "", 120);
  return useQuery({
    queryKey: qk.parse(debounced),
    queryFn: () => api.parse(debounced),
    enabled: debounced.trim().length > 0,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export interface Lookups {
  areas: Map<number, Area>;
  projects: Map<number, Project>;
  labels: Map<number, Label>;
  /** By uuid, the identifier URLs use. */
  areasByUuid: Map<string, Area>;
  projectsByUuid: Map<string, Project>;
}

export function useLookups(): Lookups {
  const areas = useAreas().data;
  const projects = useProjects().data;
  const labels = useLabels().data;
  return useMemo(
    () => ({
      areas: new Map((areas ?? []).map((a) => [a.id, a])),
      projects: new Map((projects ?? []).map((p) => [p.id, p])),
      labels: new Map((labels ?? []).map((l) => [l.id, l])),
      areasByUuid: new Map((areas ?? []).map((a) => [a.uuid, a])),
      projectsByUuid: new Map((projects ?? []).map((p) => [p.uuid, p])),
    }),
    [areas, projects, labels],
  );
}

// --- cache helpers -------------------------------------------------------------------

const TASK_PREFIXES: QueryKey[] = [["tasks"], ["agenda"], ["task"]];

/** Find a task in any cached list, agenda, or detail query. */
export function findTask(qc: QueryClient, id: number): Task | undefined {
  const direct = qc.getQueryData<Task>(qk.task(id));
  if (direct) return direct;
  for (const [, data] of qc.getQueriesData<Task[]>({ queryKey: ["tasks"] })) {
    const t = data?.find((x) => x.id === id);
    if (t) return t;
  }
  for (const [, data] of qc.getQueriesData<Agenda>({ queryKey: ["agenda"] })) {
    const t =
      data?.overdue.find((x) => x.id === id) ??
      data?.days.flatMap((d) => d.tasks).find((x) => x.id === id);
    if (t) return t;
  }
  return undefined;
}

/** Rewrite (or remove, when `fn` returns null) a task everywhere it is cached. */
export function updateTaskInCache(qc: QueryClient, id: number, fn: (t: Task) => Task | null) {
  const map = (list: Task[]) =>
    list.flatMap((t) => {
      if (t.id !== id) return [t];
      const next = fn(t);
      return next ? [next] : [];
    });
  qc.setQueriesData<Task[]>({ queryKey: ["tasks"] }, (old) => (old ? map(old) : old));
  qc.setQueriesData<Agenda>({ queryKey: ["agenda"] }, (old) =>
    old
      ? {
          ...old,
          overdue: map(old.overdue),
          days: old.days.map((d) => ({ ...d, tasks: map(d.tasks) })),
        }
      : old,
  );
  const single = qc.getQueryData<Task>(qk.task(id));
  if (single) {
    const next = fn(single);
    if (next) qc.setQueryData(qk.task(id), next);
  }
}

type Snapshot = [QueryKey, unknown][];

async function snapshot(qc: QueryClient): Promise<Snapshot> {
  await Promise.all(TASK_PREFIXES.map((queryKey) => qc.cancelQueries({ queryKey })));
  return TASK_PREFIXES.flatMap((queryKey) => qc.getQueriesData({ queryKey }));
}

function restore(qc: QueryClient, snap: Snapshot | undefined) {
  for (const [key, data] of snap ?? []) qc.setQueryData(key, data);
}

function invalidateTasks(qc: QueryClient, id?: number) {
  qc.invalidateQueries({ queryKey: ["tasks"] });
  qc.invalidateQueries({ queryKey: ["agenda"] });
  qc.invalidateQueries({ queryKey: qk.projects });
  if (id !== undefined) {
    qc.invalidateQueries({ queryKey: qk.task(id) });
    qc.invalidateQueries({ queryKey: qk.activity(id) });
  }
}

function errorToast(err: unknown) {
  useUI.getState().toast({
    tone: "error",
    message: err instanceof Error ? err.message : "Something went wrong",
  });
}

const OPTIMISTIC_FIELDS = [
  "title",
  "description",
  "status",
  "priority",
  "project_id",
  "area_id",
  "label_ids",
  "due_date",
  "due_time",
] as const;

// --- writes -----------------------------------------------------------------------------

export function usePatchTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TaskPatch }) => api.patchTask(id, patch),
    onMutate: async ({ id, patch }) => {
      const snap = await snapshot(qc);
      updateTaskInCache(qc, id, (t) => {
        const next: Task = { ...t };
        for (const f of OPTIMISTIC_FIELDS) {
          if (f in patch) (next as unknown as Record<string, unknown>)[f] = patch[f];
        }
        if (patch.project_id) next.area_id = null;
        if (patch.clear_recurrence) next.recurrence = null;
        return next;
      });
      return { snap };
    },
    onError: (err, _v, ctx) => {
      restore(qc, ctx?.snap);
      errorToast(err);
    },
    onSuccess: (task) => updateTaskInCache(qc, task.id, () => task),
    onSettled: (_d, _e, { id }) => invalidateTasks(qc, id),
  });
}

export function useCompleteTask() {
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const reopen = useReopenTask();
  return useMutation({
    mutationFn: (id: number) => api.complete(id),
    onMutate: async (id) => {
      const snap = await snapshot(qc);
      updateTaskInCache(qc, id, (t) =>
        // A repeating task moves to its next date; only the server knows which.
        t.recurrence ? t : { ...t, status: "done", completed_at: new Date().toISOString() },
      );
      return { snap };
    },
    onError: (err, _id, ctx) => {
      restore(qc, ctx?.snap);
      errorToast(err);
    },
    onSuccess: ({ task, open_subtasks }) => {
      updateTaskInCache(qc, task.id, () => task);
      if (task.recurrence && task.status !== "done" && task.due_date) {
        toast({ message: `${task.title}. Next: ${formatShort(task.due_date)}` });
      } else {
        toast({
          message: `Completed ${task.key}`,
          action: { label: "Undo", run: () => reopen.mutate(task.id) },
        });
      }
      if (open_subtasks > 0) {
        toast({
          tone: "warn",
          message: `${open_subtasks} open subtask${open_subtasks === 1 ? "" : "s"} left on ${task.key}`,
        });
      }
    },
    onSettled: (_d, _e, id) => invalidateTasks(qc, id),
  });
}

export function useReopenTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.reopen(id),
    onMutate: async (id) => {
      const snap = await snapshot(qc);
      updateTaskInCache(qc, id, (t) => ({ ...t, status: "todo", completed_at: null }));
      return { snap };
    },
    onError: (err, _id, ctx) => {
      restore(qc, ctx?.snap);
      errorToast(err);
    },
    onSuccess: (task) => updateTaskInCache(qc, task.id, () => task),
    onSettled: (_d, _e, id) => invalidateTasks(qc, id),
  });
}

/** Complete open tasks and reopen closed ones, as the e key and the row circle do. */
export function useToggleComplete() {
  const qc = useQueryClient();
  const complete = useCompleteTask();
  const reopen = useReopenTask();
  return (id: number) => {
    const t = findTask(qc, id);
    if (t && (t.status === "done" || t.status === "canceled")) reopen.mutate(id);
    else complete.mutate(id);
  };
}

export function useDeleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteTask(id),
    onMutate: async (id) => {
      const snap = await snapshot(qc);
      updateTaskInCache(qc, id, () => null);
      const ui = useUI.getState();
      if (ui.detailId === id) ui.closeDetail();
      return { snap };
    },
    onError: (err, _id, ctx) => {
      restore(qc, ctx?.snap);
      errorToast(err);
    },
    onSettled: () => invalidateTasks(qc),
  });
}

export function useQuickAdd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: QuickAddIn) => api.quickAdd(body),
    onError: errorToast,
    onSettled: (_d, _e, body) => {
      invalidateTasks(qc, body.parent_id ?? undefined);
      if (body.create_missing) {
        qc.invalidateQueries({ queryKey: qk.labels });
      }
    },
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TaskIn) => api.createTask(body),
    onError: errorToast,
    onSettled: (_d, _e, body) => invalidateTasks(qc, body.parent_id ?? undefined),
  });
}

export function useCommentMutations(taskId: number) {
  const qc = useQueryClient();
  const settle = () => {
    qc.invalidateQueries({ queryKey: qk.comments(taskId) });
    qc.invalidateQueries({ queryKey: qk.activity(taskId) });
    qc.invalidateQueries({ queryKey: qk.task(taskId) });
  };
  return {
    add: useMutation({
      mutationFn: (body: string) => api.addComment(taskId, body),
      onError: errorToast,
      onSettled: settle,
    }),
    edit: useMutation({
      mutationFn: ({ id, body }: { id: number; body: string }) => api.patchComment(id, body),
      onError: errorToast,
      onSettled: settle,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api.deleteComment(id),
      onError: errorToast,
      onSettled: settle,
    }),
  };
}

/** Tasks in a deleted project are kept; the server moves them to the Inbox. */
export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteProject(id),
    onSuccess: (_, id) => {
      qc.setQueryData<Project[]>(qk.projects, (old) => old?.filter((p) => p.id !== id));
    },
    onError: errorToast,
    onSettled: () => invalidateTasks(qc),
  });
}

export function useCreateLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.createLabel({ name }),
    onError: errorToast,
    onSuccess: (label) => {
      qc.setQueryData<Label[]>(qk.labels, (old) => [...(old ?? []), label]);
    },
  });
}

export function usePatchSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.patchSettings,
    onError: errorToast,
    onSuccess: (s) => {
      qc.setQueryData(qk.settings, s);
      qc.invalidateQueries({ queryKey: ["agenda"] });
      useUI.getState().toast({ message: `Time zone set to ${s.timezone}` });
    },
  });
}
