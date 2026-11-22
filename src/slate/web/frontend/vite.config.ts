import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The backend refuses cookie-authenticated writes whose Origin does not match
// the Host header, so the proxy keeps the browser's Host (no changeOrigin).
const backend = { target: "http://localhost:8000", changeOrigin: false };

export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    proxy: {
      "/api": backend,
      "/auth": backend,
    },
  },
});
