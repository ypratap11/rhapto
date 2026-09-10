import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    // jsdom + Base UI + userEvent typing is slow on some hosts; 5s produced spurious timeouts.
    testTimeout: 20000,
  },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
});
