import { describe, expect, it } from "vitest";
import type { Token } from "./api";
import { buildSpans } from "./tokens";

const tok = (kind: string, text: string, start: number, unresolved = false): Token => ({
  kind,
  text,
  start,
  end: start + text.length,
  unresolved,
});

const joined = (spans: { text: string }[]) => spans.map((s) => s.text).join("");

describe("buildSpans", () => {
  it("splits text around tokens in order", () => {
    const text = "Buy milk tomorrow #home p2";
    const spans = buildSpans(text, [
      tok("priority", "p2", 24),
      tok("date", "tomorrow", 9),
      tok("project", "#home", 18),
    ]);
    expect(spans.map((s) => [s.text, s.kind])).toEqual([
      ["Buy milk ", null],
      ["tomorrow", "date"],
      [" ", null],
      ["#home", "project"],
      [" ", null],
      ["p2", "priority"],
    ]);
    expect(joined(spans)).toBe(text);
  });

  it("keeps the unresolved flag", () => {
    const spans = buildSpans("Plan #garden", [tok("project", "#garden", 5, true)]);
    expect(spans[1]).toMatchObject({ kind: "project", unresolved: true, start: 5 });
  });

  it("drops stale tokens whose range no longer holds their text", () => {
    // Parsed "Call mom today", then the user typed "Call my mom today".
    const text = "Call my mom today";
    const spans = buildSpans(text, [tok("date", "today", 9)]);
    expect(spans).toEqual([{ text, start: 0, kind: null, unresolved: false }]);
  });

  it("drops out-of-range and overlapping tokens", () => {
    const text = "every day p1";
    const spans = buildSpans(text, [
      tok("recurrence", "every day", 0),
      tok("date", "day", 6),
      tok("priority", "p1", 10),
      { kind: "label", text: "@x", start: 40, end: 42, unresolved: false },
    ]);
    expect(spans.map((s) => s.kind)).toEqual(["recurrence", null, "priority"]);
    expect(joined(spans)).toBe(text);
  });

  it("returns no spans for empty text", () => {
    expect(buildSpans("", [])).toEqual([]);
  });
});
