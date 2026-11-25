import type { Meta, StoryObj } from "@storybook/react-vite";
import type { SlateParams } from "./StoryApp";
import { aid, pid } from "./mockApi";

/** Whole-app screens: the real shell and route tree against the mock API. */
const meta: Meta = {
  title: "Screens",
  render: () => <></>,
};
export default meta;

type Story = StoryObj;
const screen = (slate: SlateParams, dark = false): Story => ({
  parameters: { slate },
  ...(dark ? { globals: { theme: "dark" } } : {}),
});

export const Today = screen({ route: "/today" });
export const TodayDark = screen({ route: "/today" }, true);
export const TodayEmpty = screen({ route: "/today", scenario: "empty" });
export const TodayLoading = screen({ route: "/today", scenario: "loading" });
export const Upcoming = screen({ route: "/upcoming" });
export const UpcomingDark = screen({ route: "/upcoming" }, true);
export const Inbox = screen({ route: "/inbox" });
export const InboxEmpty = screen({ route: "/inbox", scenario: "empty" });
export const AllTasks = screen({ route: "/all" });
export const Projects = screen({ route: "/projects" });
export const ProjectsEmpty = screen({ route: "/projects", scenario: "empty" });
export const ProjectList = screen({ route: `/projects/${pid(1)}` });
export const ProjectBoard = screen({ route: `/projects/${pid(1)}?view=board` });
export const ProjectBoardDark = screen({ route: `/projects/${pid(1)}?view=board` }, true);
export const Area = screen({ route: `/areas/${aid(1)}` });
export const PendingChanges = screen({ route: "/pending" });
export const PendingChangesDark = screen({ route: "/pending" }, true);
export const PendingChangesEmpty = screen({ route: "/pending", scenario: "empty" });
export const Settings = screen({ route: "/settings" });
export const ServerDown = screen({ route: "/today", scenario: "error" });
