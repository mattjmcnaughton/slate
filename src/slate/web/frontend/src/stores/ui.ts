import { create } from "zustand";

export type MenuKind = "status" | "priority" | "labels" | "due" | "project";

export interface MenuState {
  kind: MenuKind;
  taskIds: string[];
  /** Where to open; defaults to the selected row. */
  anchor?: { x: number; y: number };
}

export interface Toast {
  id: number;
  message: string;
  tone?: "info" | "warn" | "error";
  action?: { label: string; run: () => void };
}

export interface ConfirmState {
  title: string;
  body?: string;
  confirmLabel: string;
  onConfirm: () => void;
}

/** What the current page contributes to quick add and to page-level keys. */
export interface PageContext {
  projectId?: string | null;
  areaId?: string | null;
  /** New tasks without a date get today's date (Today page). */
  dueToday?: boolean;
  toggleView?: () => void;
}

interface UIState {
  // Keyboard cursor and multi-select over the visible list.
  visibleIds: string[];
  selectedId: string | null;
  checkedIds: string[];
  setVisible: (ids: string[]) => void;
  select: (id: string | null) => void;
  move: (delta: number) => void;
  toggleChecked: (id: string) => void;
  clearChecked: () => void;

  detailId: string | null;
  openDetail: (id: string) => void;
  closeDetail: () => void;

  palette: null | "commands" | "search";
  setPalette: (p: UIState["palette"]) => void;

  quickAdd: boolean;
  setQuickAdd: (open: boolean) => void;
  /** Set by an inline quick-add line on the page so "c" can focus it instead. */
  inlineQuickAdd: (() => void) | null;
  setInlineQuickAdd: (focus: (() => void) | null) => void;

  menu: MenuState | null;
  openMenu: (m: MenuState) => void;
  closeMenu: () => void;

  confirm: ConfirmState | null;
  setConfirm: (c: ConfirmState | null) => void;

  shortcuts: boolean;
  setShortcuts: (open: boolean) => void;

  /** The assistant panel (Ctrl/Cmd J). */
  assistant: boolean;
  setAssistant: (open: boolean) => void;

  page: PageContext;
  setPage: (p: PageContext) => void;

  toasts: Toast[];
  toast: (t: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
}

let toastSeq = 0;

export const useUI = create<UIState>((set, get) => ({
  visibleIds: [],
  selectedId: null,
  checkedIds: [],
  setVisible: (ids) =>
    set((s) => ({
      visibleIds: ids,
      checkedIds: s.checkedIds.filter((id) => ids.includes(id)),
    })),
  select: (id) => set({ selectedId: id }),
  move: (delta) => {
    const { visibleIds, selectedId, detailId } = get();
    if (visibleIds.length === 0) return;
    const at = selectedId === null ? -1 : visibleIds.indexOf(selectedId);
    const next =
      at === -1
        ? delta > 0
          ? 0
          : visibleIds.length - 1
        : Math.min(visibleIds.length - 1, Math.max(0, at + delta));
    const id = visibleIds[next];
    // With the detail pane open, moving the cursor follows along in the pane.
    set({ selectedId: id, detailId: detailId === null ? null : id });
  },
  toggleChecked: (id) =>
    set((s) => ({
      checkedIds: s.checkedIds.includes(id)
        ? s.checkedIds.filter((x) => x !== id)
        : [...s.checkedIds, id],
    })),
  clearChecked: () => set({ checkedIds: [] }),

  detailId: null,
  openDetail: (id) => set({ detailId: id, selectedId: id }),
  closeDetail: () => set({ detailId: null }),

  palette: null,
  setPalette: (palette) => set({ palette }),

  quickAdd: false,
  setQuickAdd: (quickAdd) => set({ quickAdd }),
  inlineQuickAdd: null,
  setInlineQuickAdd: (inlineQuickAdd) => set({ inlineQuickAdd }),

  menu: null,
  openMenu: (menu) => set({ menu }),
  closeMenu: () => set({ menu: null }),

  confirm: null,
  setConfirm: (confirm) => set({ confirm }),

  shortcuts: false,
  setShortcuts: (shortcuts) => set({ shortcuts }),

  assistant: false,
  setAssistant: (assistant) => set({ assistant }),

  page: {},
  setPage: (page) => set({ page }),

  toasts: [],
  toast: (t) => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id }] }));
    window.setTimeout(() => get().dismissToast(id), t.action ? 6000 : 4000);
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** The tasks a list command acts on: the checked set, else the selected row. */
export function targetIds(): string[] {
  const { checkedIds, selectedId } = useUI.getState();
  if (checkedIds.length) return checkedIds;
  return selectedId === null ? [] : [selectedId];
}

export function anyLayerOpen(): boolean {
  const s = useUI.getState();
  return Boolean(s.palette || s.quickAdd || s.menu || s.confirm || s.shortcuts);
}
