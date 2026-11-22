import { create } from "zustand";

export type Theme = "light" | "dark";

const KEY = "slate-theme";

function initial(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Storage unavailable; fall back to the OS preference.
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

interface ThemeState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => {
  const theme = initial();
  apply(theme);
  return {
    theme,
    setTheme: (t) => {
      apply(t);
      try {
        localStorage.setItem(KEY, t);
      } catch {
        // Not persisted; the choice still applies to this tab.
      }
      set({ theme: t });
    },
    toggle: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
  };
});
