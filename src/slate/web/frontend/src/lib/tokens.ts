import type { Token } from "./api";

export interface Span {
  text: string;
  start: number;
  /** null for plain title text. */
  kind: string | null;
  unresolved: boolean;
}

/**
 * Split `text` into plain and highlighted spans from parser tokens.
 *
 * Tokens may be stale (parsed from an earlier keystroke while the next parse is
 * in flight), out of order, overlapping, or out of range. A token is used only if
 * its range still holds exactly its text; overlapping tokens after the first are
 * dropped. The spans always concatenate back to `text`.
 */
export function buildSpans(text: string, tokens: readonly Token[]): Span[] {
  const usable = tokens
    .filter(
      (t) =>
        t.start >= 0 &&
        t.end > t.start &&
        t.end <= text.length &&
        text.slice(t.start, t.end) === t.text,
    )
    .sort((a, b) => a.start - b.start);

  const spans: Span[] = [];
  let pos = 0;
  for (const t of usable) {
    if (t.start < pos) continue;
    if (t.start > pos) {
      spans.push({ text: text.slice(pos, t.start), start: pos, kind: null, unresolved: false });
    }
    spans.push({ text: t.text, start: t.start, kind: t.kind, unresolved: t.unresolved });
    pos = t.end;
  }
  if (pos < text.length) {
    spans.push({ text: text.slice(pos), start: pos, kind: null, unresolved: false });
  }
  return spans;
}
