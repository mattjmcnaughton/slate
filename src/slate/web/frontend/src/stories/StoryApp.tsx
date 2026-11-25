import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  type AnyRouter,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router";
import { type ReactNode, createContext, useContext, useEffect, useState } from "react";
import { routeTree } from "../routeTree.gen";
import { useUI } from "../stores/ui";
import { type Scenario, resetMockApi } from "./mockApi";

type UIState = ReturnType<typeof useUI.getState>;

/** Per-story settings, read from `parameters.slate`. */
export interface SlateParams {
  /** Render the whole app (shell and page) at this path; otherwise just the story. */
  route?: string;
  scenario?: Scenario;
  /** UI store state to open, such as the palette, quick add, or a task's detail. */
  ui?: Partial<UIState>;
}

const RESET: Partial<UIState> = {
  visibleIds: [],
  selectedId: null,
  checkedIds: [],
  detailId: null,
  palette: null,
  quickAdd: false,
  inlineQuickAdd: null,
  menu: null,
  confirm: null,
  shortcuts: false,
  assistant: false,
  page: {},
  toasts: [],
};

const StoryContent = createContext<ReactNode>(null);
const Content = () => <>{useContext(StoryContent)}</>;

/**
 * Fresh mock data, query cache, UI store, and router for each story. Components
 * get a bare router (they use links and navigation); screens get the real route tree.
 */
export function StoryApp({ params, children }: { params: SlateParams; children: ReactNode }) {
  const [env] = useState(() => {
    resetMockApi(params.scenario ?? "demo");
    // Screens get their UI state once the page is up (below); components get it now.
    useUI.setState({ ...RESET, ...(params.route ? {} : params.ui) });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 15_000 } },
    });
    const history = createMemoryHistory({ initialEntries: [params.route ?? "/"] });
    const router: AnyRouter = params.route
      ? createRouter({ routeTree, history, context: { queryClient } })
      : createRouter({ routeTree: createRootRoute({ component: Content }), history });
    return { queryClient, router };
  });

  // The shell clears the selection and detail pane when its route first renders,
  // so open layers only after that, as a keypress would.
  useEffect(() => {
    if (!params.route || !params.ui) return;
    const ui = params.ui;
    const t = window.setTimeout(() => useUI.setState(ui), 400);
    return () => window.clearTimeout(t);
  }, [params.route, params.ui]);

  return (
    <QueryClientProvider client={env.queryClient}>
      <StoryContent.Provider value={children}>
        <RouterProvider router={env.router} />
      </StoryContent.Provider>
    </QueryClientProvider>
  );
}
