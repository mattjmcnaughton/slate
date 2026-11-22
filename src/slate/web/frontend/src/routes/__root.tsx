import type { QueryClient } from "@tanstack/react-query";
import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";
import { Shell } from "../components/Shell";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: () => (
    <Shell>
      <Outlet />
    </Shell>
  ),
  notFoundComponent: () => (
    <div className="px-5 py-16 text-center text-[14px] text-ink2">
      This page does not exist. Press <kbd className="kbd">G</kbd> <kbd className="kbd">T</kbd> for
      Today.
    </div>
  ),
});
