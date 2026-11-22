import { describe, expect, it, vi } from "vitest";
import { type Binding, comboOf, createDispatcher } from "./keys";

function press(key: string, target: EventTarget = document.body, init: KeyboardEventInit = {}) {
  const e = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  Object.defineProperty(e, "target", { value: target });
  return e;
}

describe("comboOf", () => {
  it("normalizes modifiers and named keys", () => {
    expect(comboOf(press("k", document.body, { metaKey: true }))).toBe("mod+k");
    expect(comboOf(press("K", document.body, { ctrlKey: true, shiftKey: true }))).toBe("mod+k");
    expect(comboOf(press("?", document.body, { shiftKey: true }))).toBe("?");
    expect(comboOf(press("Enter", document.body, { shiftKey: true }))).toBe("shift+enter");
    expect(comboOf(press("Escape"))).toBe("escape");
  });
});

describe("createDispatcher", () => {
  function setup(extra: Partial<Binding>[] = []) {
    const calls: string[] = [];
    const bindings: Binding[] = [
      { keys: "c", run: () => calls.push("c") },
      { keys: "mod+k", run: () => calls.push("palette"), allowInInput: true },
      { keys: "g t", run: () => calls.push("today") },
      { keys: "g i", run: () => calls.push("inbox") },
      ...extra.map((b) => ({ keys: "", run: () => {}, ...b })),
    ];
    let clock = 0;
    const dispatch = createDispatcher(() => bindings, { now: () => clock });
    return {
      calls,
      dispatch,
      tick: (ms: number) => {
        clock += ms;
      },
    };
  }

  it("fires single keys outside fields", () => {
    const { calls, dispatch } = setup();
    const e = press("c");
    expect(dispatch(e)).toBe(true);
    expect(e.defaultPrevented).toBe(true);
    expect(calls).toEqual(["c"]);
  });

  it("never fires single keys while typing in an input, textarea, or contenteditable", () => {
    const { calls, dispatch } = setup();
    const input = document.createElement("input");
    const textarea = document.createElement("textarea");
    const editable = document.createElement("div");
    editable.contentEditable = "true";
    Object.defineProperty(editable, "isContentEditable", { value: true });
    for (const target of [input, textarea, editable]) {
      expect(dispatch(press("c", target))).toBe(false);
      expect(dispatch(press("g", target))).toBe(false);
      expect(dispatch(press("t", target))).toBe(false);
    }
    expect(calls).toEqual([]);
  });

  it("still fires bindings that allow inputs, such as mod+k", () => {
    const { calls, dispatch } = setup();
    dispatch(press("k", document.createElement("input"), { ctrlKey: true }));
    expect(calls).toEqual(["palette"]);
  });

  it("treats checkboxes as non-editable", () => {
    const { calls, dispatch } = setup();
    const box = document.createElement("input");
    box.type = "checkbox";
    dispatch(press("c", box));
    expect(calls).toEqual(["c"]);
  });

  it("does not treat mod+c (copy) as c", () => {
    const { calls, dispatch } = setup();
    expect(dispatch(press("c", document.body, { metaKey: true }))).toBe(false);
    expect(calls).toEqual([]);
  });

  it("runs two-key sequences within the timeout", () => {
    const { calls, dispatch, tick } = setup();
    dispatch(press("g"));
    tick(300);
    dispatch(press("t"));
    expect(calls).toEqual(["today"]);
  });

  it("drops a sequence prefix after the timeout", () => {
    const { calls, dispatch, tick } = setup();
    dispatch(press("g"));
    tick(1500);
    expect(dispatch(press("t"))).toBe(false);
    dispatch(press("c"));
    expect(calls).toEqual(["c"]);
  });

  it("skips bindings whose when() is false", () => {
    const run = vi.fn();
    const { dispatch } = setup([{ keys: "e", run, when: () => false }]);
    expect(dispatch(press("e"))).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it("ignores IME composition", () => {
    const { calls, dispatch } = setup();
    dispatch(press("c", document.body, { isComposing: true }));
    expect(calls).toEqual([]);
  });
});
