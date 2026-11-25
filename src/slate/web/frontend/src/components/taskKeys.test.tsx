import { act, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { useUI } from "../stores/ui";
import { StoryApp } from "../stories/StoryApp";
import { installMockApi, tid } from "../stories/mockApi";

// A key built from a task's UUID instead of its per-workspace number.
const UUID_KEY = /SLT-[0-9a-f]{8}-/;

beforeAll(() => {
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }) as never;
  Element.prototype.scrollIntoView = () => {};
  window.scrollTo = () => {};
  installMockApi();
});

async function renderApp(route: string) {
  const view = render(<StoryApp params={{ route }}>{null}</StoryApp>);
  // Let the shell clear its first-render selection before a test sets one.
  await act(() => new Promise((r) => setTimeout(r, 200)));
  return view;
}

describe("task keys", () => {
  it("All tasks, the footer, and the detail pane show SLT-n, not the id", async () => {
    const { container } = await renderApp("/all");
    const row = (await screen.findByText("Measure the backsplash area")).closest("tr");
    expect(within(row as HTMLElement).getByText("SLT-10 ›")).toBeTruthy();

    act(() => useUI.setState({ selectedId: tid(12) }));
    expect(within(screen.getByRole("contentinfo")).getByText("SLT-12")).toBeTruthy();

    act(() => useUI.setState({ detailId: tid(12) }));
    const detail = await screen.findByRole("complementary", { name: "Task detail" });
    expect(within(detail).getByText("SLT-12")).toBeTruthy();

    expect(container.textContent).not.toMatch(UUID_KEY);
  });
});
