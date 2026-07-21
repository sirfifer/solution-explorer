import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Provide the build-time maturity gate constant (card R3) to the test runtime.
  // Default false (production-like) so guarded experimental code is inert; tests
  // that exercise the experimental-build branch pass the flag explicitly to
  // resolveChannel rather than relying on this global.
  define: {
    __EXPERIMENTAL_BUILD__: "false",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/__tests__/**", "src/vite-env.d.ts"],
    },
  },
});
