// Global keyboard shortcuts. Bindings are strings such as "c", "?", "mod+k",
// "escape", "shift+enter", or two-key sequences such as "g t".

export interface Binding {
  keys: string;
  run: (e: KeyboardEvent) => void;
  /** Fire even when focus is in an input, textarea, select, or contenteditable. */
  allowInInput?: boolean;
  /** Skip the binding when this returns false. */
  when?: () => boolean;
}

const NAMED: Record<string, string> = {
  " ": "space",
  Escape: "escape",
  Esc: "escape",
  Enter: "enter",
  Backspace: "backspace",
  Delete: "delete",
  ArrowUp: "arrowup",
  ArrowDown: "arrowdown",
  ArrowLeft: "arrowleft",
  ArrowRight: "arrowright",
  Tab: "tab",
};

/** Normalize an event to a combo such as "mod+k", "escape", "?" or "j". */
export function comboOf(
  e: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "shiftKey">,
) {
  const named = NAMED[e.key];
  const key = named ?? (e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase());
  const parts: string[] = [];
  if (e.metaKey || e.ctrlKey) parts.push("mod");
  if (e.altKey) parts.push("alt");
  // Shift is part of printable characters already ("?" not "shift+/").
  if (e.shiftKey && (named || key.length > 1)) parts.push("shift");
  parts.push(key);
  return parts.join("+");
}

export function isEditable(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (target as HTMLInputElement).type;
    return !["checkbox", "radio", "button", "submit", "reset", "range", "color"].includes(type);
  }
  return false;
}

export interface DispatcherOptions {
  /** How long the second key of a sequence may wait, in ms. */
  sequenceTimeout?: number;
  now?: () => number;
}

/**
 * Build a keydown handler. It returns true when a binding ran (and prevents the
 * default action). Single keys never fire while typing in a field unless the
 * binding sets `allowInInput`.
 */
export function createDispatcher(
  getBindings: () => readonly Binding[],
  { sequenceTimeout = 1000, now = () => Date.now() }: DispatcherOptions = {},
) {
  let pending: { key: string; at: number } | null = null;

  return function dispatch(e: KeyboardEvent): boolean {
    if (e.isComposing || e.defaultPrevented) return false;
    if (["Shift", "Meta", "Control", "Alt"].includes(e.key)) return false;
    const combo = comboOf(e);
    const inField = isEditable(e.target);
    const bindings = getBindings().filter(
      (b) => (b.allowInInput || !inField) && (b.when?.() ?? true),
    );

    const prefix = pending && now() - pending.at <= sequenceTimeout ? pending.key : null;
    pending = null;

    if (prefix) {
      const seq = bindings.find((b) => b.keys === `${prefix} ${combo}`);
      if (seq) {
        e.preventDefault();
        seq.run(e);
        return true;
      }
    }

    const single = bindings.find((b) => b.keys === combo);
    if (single) {
      e.preventDefault();
      single.run(e);
      return true;
    }

    if (bindings.some((b) => b.keys.startsWith(`${combo} `))) {
      pending = { key: combo, at: now() };
      e.preventDefault();
      return true;
    }
    return false;
  };
}

/** Display form of a combo for kbd chips: "mod+k" -> ["⌘", "K"] on macOS. */
export function keyLabels(keys: string): string[] {
  const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
  return keys.split(/[ +]/).map((k) => {
    switch (k) {
      case "mod":
        return mac ? "⌘" : "Ctrl";
      case "shift":
        return "⇧";
      case "alt":
        return mac ? "⌥" : "Alt";
      case "enter":
        return "↵";
      case "escape":
        return "Esc";
      case "backspace":
        return "⌫";
      case "arrowup":
        return "↑";
      case "arrowdown":
        return "↓";
      default:
        return k.length === 1 ? k.toUpperCase() : k;
    }
  });
}
