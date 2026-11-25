import "@fontsource-variable/inter";
import "@fontsource/newsreader/400.css";
import "@fontsource/newsreader/400-italic.css";
import "@fontsource/newsreader/500.css";
import "../src/index.css";
import type { Decorator, Preview } from "@storybook/react-vite";
import { type Theme, useTheme } from "../src/stores/theme";
import { StoryApp } from "../src/stories/StoryApp";
import { installMockApi } from "../src/stories/mockApi";

installMockApi();

const withSlate: Decorator = (Story, ctx) => {
  useTheme.getState().setTheme(ctx.globals.theme as Theme);
  const params = ctx.parameters.slate ?? {};
  // Screens fill the frame like the app does; components sit on the page background.
  return (
    <div className={params.route ? "h-screen" : "min-h-screen bg-bg p-6 text-ink"}>
      <StoryApp key={ctx.id} params={params}>
        {params.route ? null : <Story />}
      </StoryApp>
    </div>
  );
};

const preview: Preview = {
  globalTypes: {
    theme: {
      description: "Slate theme",
      toolbar: {
        title: "Theme",
        icon: "mirror",
        items: [
          { value: "light", title: "Light (Daybook)", icon: "sun" },
          { value: "dark", title: "Dark (Ledger)", icon: "moon" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  parameters: {
    layout: "fullscreen",
    controls: { expanded: true },
    options: { storySort: { order: ["Screens", "Overlays", "Components"] } },
  },
  decorators: [withSlate],
};

export default preview;
