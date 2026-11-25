import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  framework: "@storybook/react-vite",
  core: { disableTelemetry: true },
  // Served behind a proxy (an Amp portal) as well as on localhost.
  viteFinal: (vite) => ({ ...vite, server: { ...vite.server, allowedHosts: true } }),
};

export default config;
