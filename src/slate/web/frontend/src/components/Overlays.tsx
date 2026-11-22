import { useEffect, useRef } from "react";
import { keyLabels } from "../lib/keys";
import { useUI } from "../stores/ui";
import { IconClose } from "./icons";

export function Keys({ keys }: { keys: string }) {
  return (
    <span className="inline-flex gap-1">
      {keyLabels(keys).map((k, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static key chips
        <kbd key={i} className="kbd">
          {k}
        </kbd>
      ))}
    </span>
  );
}

export function Toasts() {
  const toasts = useUI((s) => s.toasts);
  const dismiss = useUI((s) => s.dismissToast);
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[calc(76px+env(safe-area-inset-bottom))] z-[60] flex flex-col items-center gap-2 px-3 desk:bottom-10 desk:items-end desk:px-5"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`popover anim-rise pointer-events-auto flex max-w-[420px] items-center gap-3 px-3.5 py-2 text-[13px] ${
            t.tone === "error" ? "text-red" : t.tone === "warn" ? "text-amber" : "text-ink"
          }`}
        >
          <span className="min-w-0 flex-1">{t.message}</span>
          {t.action && (
            <button
              type="button"
              className="font-medium text-accent hover:underline"
              onClick={() => {
                t.action?.run();
                dismiss(t.id);
              }}
            >
              {t.action.label}
            </button>
          )}
          <button
            type="button"
            aria-label="Dismiss"
            className="text-ink3 hover:text-ink"
            onClick={() => dismiss(t.id)}
          >
            <IconClose size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function ConfirmDialog() {
  const confirm = useUI((s) => s.confirm);
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (confirm) ref.current?.focus();
  }, [confirm]);
  if (!confirm) return null;
  const close = () => useUI.getState().setConfirm(null);
  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-ink/25 px-4">
      <button
        type="button"
        aria-label="Cancel"
        className="absolute inset-0 cursor-default"
        onClick={close}
      />
      <div
        role="alertdialog"
        aria-label={confirm.title}
        className="popover anim-rise relative w-full max-w-[400px] p-5"
      >
        <h2 className="text-[15px] font-semibold">{confirm.title}</h2>
        {confirm.body && (
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink2">{confirm.body}</p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={close}
            className="h-8 rounded-md border border-line2 px-3 text-[13px] text-ink2 hover:bg-hover"
          >
            Cancel
          </button>
          <button
            ref={ref}
            type="button"
            onClick={() => {
              close();
              confirm.onConfirm();
            }}
            className="h-8 rounded-md bg-red px-3 text-[13px] font-medium text-white hover:opacity-90"
          >
            {confirm.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

const SHEET: { title: string; rows: [string, string][] }[] = [
  {
    title: "Anywhere",
    rows: [
      ["mod+k", "Command palette"],
      ["c", "Add a task"],
      ["/", "Search"],
      ["?", "This sheet"],
      ["escape", "Close the top layer"],
    ],
  },
  {
    title: "Go to",
    rows: [
      ["g t", "Today"],
      ["g u", "Upcoming"],
      ["g i", "Inbox"],
      ["g a", "All tasks"],
      ["g p", "Projects"],
    ],
  },
  {
    title: "In lists",
    rows: [
      ["j", "Next task"],
      ["k", "Previous task"],
      ["enter", "Open"],
      ["x", "Select (multi)"],
      ["e", "Complete"],
      ["s", "Status"],
      ["p", "Priority"],
      ["d", "Due date"],
      ["l", "Labels"],
      ["m", "Move to project"],
      ["v", "List or board"],
      ["backspace", "Delete"],
    ],
  },
];

export function ShortcutSheet() {
  const open = useUI((s) => s.shortcuts);
  if (!open) return null;
  const close = () => useUI.getState().setShortcuts(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/20 px-4">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 cursor-default"
        onClick={close}
      />
      <div
        role="dialog"
        aria-label="Keyboard shortcuts"
        className="popover anim-rise relative max-h-[80vh] w-full max-w-[640px] overflow-y-auto p-5"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold">Keyboard shortcuts</h2>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="text-ink3 hover:text-ink"
          >
            <IconClose />
          </button>
        </div>
        <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          {SHEET.map((group) => (
            <section key={group.title}>
              <h3 className="mb-1.5 text-[12px] font-medium text-ink3">{group.title}</h3>
              {group.rows.map(([keys, label]) => (
                <div
                  key={keys}
                  className="flex h-7 items-center justify-between text-[13px] text-ink2"
                >
                  <span>{label}</span>
                  <Keys keys={keys} />
                </div>
              ))}
            </section>
          ))}
        </div>
        <p className="mt-4 text-[12px] text-ink3">
          Menus take digit keys: press s then 3 for In progress.
        </p>
      </div>
    </div>
  );
}
