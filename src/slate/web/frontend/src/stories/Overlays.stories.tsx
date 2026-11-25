import type { Meta, StoryObj } from "@storybook/react-vite";
import type { SlateParams } from "./StoryApp";
import { tid } from "./mockApi";

/** Layers over a screen, opened through the UI store the keyboard shortcuts use. */
const meta: Meta = {
  title: "Overlays",
  render: () => <></>,
};
export default meta;

type Story = StoryObj;
const overlay = (slate: SlateParams, dark = false): Story => ({
  parameters: { slate: { route: "/today", ...slate } },
  ...(dark ? { globals: { theme: "dark" } } : {}),
});

export const TaskDetail = overlay({ ui: { detailId: tid(10), selectedId: tid(10) } });
export const TaskDetailDark = overlay({ ui: { detailId: tid(10), selectedId: tid(10) } }, true);
export const TaskDetailRecurring = overlay({ ui: { detailId: tid(8), selectedId: tid(8) } });
export const TaskDetailLoading = overlay({ scenario: "loading", ui: { detailId: tid(10) } });
export const QuickAddModal = overlay({ route: "/projects", ui: { quickAdd: true } });
export const QuickAddModalDark = overlay({ route: "/projects", ui: { quickAdd: true } }, true);
export const CommandPalette = overlay({ ui: { palette: "commands" } });
export const CommandPaletteDark = overlay({ ui: { palette: "commands" } }, true);
export const CommandPaletteWithSelection = overlay({
  ui: { palette: "commands", selectedId: tid(1), checkedIds: [tid(1), tid(28)] },
});
export const Search = overlay({ ui: { palette: "search" } });
export const StatusMenu = overlay({
  ui: { selectedId: tid(1), menu: { kind: "status", taskIds: [tid(1)] } },
});
export const DueMenu = overlay({
  ui: { selectedId: tid(1), menu: { kind: "due", taskIds: [tid(1)] } },
});
export const LabelsMenu = overlay({
  ui: { selectedId: tid(1), menu: { kind: "labels", taskIds: [tid(1)] } },
});
export const MoveMenu = overlay({
  ui: { selectedId: tid(1), menu: { kind: "project", taskIds: [tid(1)] } },
});
export const ShortcutSheet = overlay({ ui: { shortcuts: true } });
export const ConfirmDelete = overlay({
  ui: {
    confirm: {
      title: "Delete SLT-1?",
      body: "“Call the dentist to reschedule” and its comments and activity will be removed. This cannot be undone.",
      confirmLabel: "Delete",
      onConfirm: () => {},
    },
  },
});
export const Toasts = overlay({
  ui: {
    toasts: [
      { id: 1, message: "Completed SLT-1", action: { label: "Undo", run: () => {} } },
      { id: 2, tone: "warn", message: "1 open subtask left on SLT-10" },
      { id: 3, tone: "error", message: "Service unavailable" },
    ],
  },
});
export const Assistant = overlay({ ui: { assistant: true } });
export const AssistantDark = overlay({ ui: { assistant: true } }, true);
