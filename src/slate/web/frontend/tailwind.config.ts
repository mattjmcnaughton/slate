import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        panel: v("panel"),
        raise: v("raise"),
        hover: v("hover"),
        line: v("line"),
        line2: v("line2"),
        ink: v("ink"),
        ink2: v("ink2"),
        ink3: v("ink3"),
        accent: v("accent"),
        "accent-soft": "var(--accent-soft)",
        red: v("red"),
        amber: v("amber"),
        blue: v("blue"),
        plum: v("plum"),
        teal: v("teal"),
      },
      fontFamily: {
        sans: [
          '"Inter Variable"',
          "Inter",
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
        serif: ["Newsreader", '"Iowan Old Style"', '"Palatino Linotype"', "Georgia", "serif"],
        mono: ["ui-monospace", '"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
      screens: {
        // Phone layout is <= 640px; everything above is the desktop structure.
        desk: "641px",
      },
    },
  },
  plugins: [],
} satisfies Config;
