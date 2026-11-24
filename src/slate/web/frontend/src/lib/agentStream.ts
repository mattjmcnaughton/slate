// Sends one message to the assistant and reads its server-sent events.

import { ApiError, type PendingChange } from "./api";

export interface AppliedEvent {
  tool: string;
  summary: string;
  /** Catalog task rows; free text arrives as {untrusted: "..."}. */
  tasks: Record<string, unknown>[];
}

export type AgentEvent =
  | { type: "delta"; text: string }
  | { type: "tool"; name: string; status: "started" | "done" | "failed" }
  | { type: "pending_change"; change: PendingChange }
  | { type: "applied"; applied: AppliedEvent }
  | { type: "done"; message_id: string; pending_change_ids: string[] }
  | { type: "error"; code: string; message: string };

export interface SendInput {
  content: string;
  images: File[];
  screen?: string;
}

function toEvent(name: string, data: Record<string, unknown>): AgentEvent | null {
  switch (name) {
    case "delta":
      return { type: "delta", text: String(data.text ?? "") };
    case "tool":
      return { type: "tool", name: String(data.name), status: data.status as "done" };
    case "pending_change":
      return { type: "pending_change", change: data as unknown as PendingChange };
    case "applied":
      return { type: "applied", applied: data as unknown as AppliedEvent };
    case "done":
      return {
        type: "done",
        message_id: String(data.message_id),
        pending_change_ids: (data.pending_change_ids as string[]) ?? [],
      };
    case "error":
      return { type: "error", code: String(data.code), message: String(data.message) };
    default:
      return null;
  }
}

/** Parse complete frames out of `buffer`; returns events and the unparsed rest. */
export function parseFrames(buffer: string): { events: AgentEvent[]; rest: string } {
  const events: AgentEvent[] = [];
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  for (const frame of frames) {
    let name = "";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event: ")) name = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (!name || !data) continue;
    const ev = toEvent(name, JSON.parse(data));
    if (ev) events.push(ev);
  }
  return { events, rest };
}

export async function sendMessage(
  input: SendInput,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append("content", input.content);
  if (input.screen) form.append("screen", input.screen);
  for (const f of input.images) form.append("images", f);
  const res = await fetch("/api/agent/messages", {
    method: "POST",
    body: form,
    credentials: "same-origin",
    signal,
  });
  if (!res.ok || !res.body) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const detail = (await res.json()).detail;
      message = typeof detail === "string" ? detail : (detail?.message ?? message);
    } catch {
      // keep the status line
    }
    throw new ApiError(res.status, message);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const { events, rest } = parseFrames(buffer);
    buffer = rest;
    for (const e of events) onEvent(e);
  }
}

/** Free text from the catalog is wrapped as {untrusted: "..."}; show it as plain text. */
export function plain(v: unknown): string {
  if (v && typeof v === "object" && "untrusted" in v)
    return String((v as { untrusted: unknown }).untrusted);
  return v == null ? "" : String(v);
}
