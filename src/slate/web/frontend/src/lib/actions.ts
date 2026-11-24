import { useQueryClient } from "@tanstack/react-query";
import { useUI } from "../stores/ui";
import type { TaskPatch, TaskStatus } from "./api";
import { findTask, useCompleteTask, useDeleteTask, usePatchTask, useReopenTask } from "./queries";

/** Task commands shared by keys, menus, the palette, the board, and the detail pane. */
export function useTaskActions() {
  const qc = useQueryClient();
  const patch = usePatchTask();
  const complete = useCompleteTask();
  const reopen = useReopenTask();
  const remove = useDeleteTask();
  const ui = useUI;

  const isClosed = (id: string) => {
    const s = findTask(qc, id)?.status;
    return s === "done" || s === "canceled";
  };

  return {
    patch: (ids: string[], body: TaskPatch) => {
      for (const id of ids) patch.mutate({ id, patch: body });
    },
    toggleComplete: (ids: string[]) => {
      // Mixed selections complete everything first, like Linear.
      const allClosed = ids.every(isClosed);
      for (const id of ids) {
        if (allClosed) reopen.mutate(id);
        else if (!isClosed(id)) complete.mutate(id);
      }
    },
    setStatus: (ids: string[], status: TaskStatus) => {
      for (const id of ids) {
        const t = findTask(qc, id);
        if (t?.status === status) continue;
        if (status === "done") {
          // Complete goes through the run logic (repeating tasks roll forward).
          complete.mutate(id);
        } else {
          patch.mutate({ id, patch: { status } });
        }
      }
    },
    confirmDelete: (ids: string[]) => {
      if (!ids.length) return;
      const first = findTask(qc, ids[0]);
      ui.getState().setConfirm({
        title:
          ids.length === 1 ? `Delete ${first?.key ?? "this task"}?` : `Delete ${ids.length} tasks?`,
        body:
          ids.length === 1 && first
            ? `“${first.title}” and its comments and activity will be removed. This cannot be undone.`
            : "Their comments and activity will be removed. This cannot be undone.",
        confirmLabel: "Delete",
        onConfirm: () => {
          for (const id of ids) remove.mutate(id);
          ui.getState().clearChecked();
          ui.getState().toast({
            message: ids.length === 1 ? "Task deleted" : `${ids.length} tasks deleted`,
          });
        },
      });
    },
  };
}
