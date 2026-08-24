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
    // Unit tests only, and every one of them lives under src/.
    //
    // Scoped deliberately. The default include is repo-wide, which swept in the
    // Playwright crawl specs under tests/crawl/. Those import @playwright/test,
    // which does nothing useful outside a Playwright runner and never returns,
    // so `npm test` collected them and hung with no output at all: no failure,
    // no test names, nothing to read. Two runners in one package need two
    // non-overlapping file sets, stated rather than assumed.
    include: ["src/**/*.{test,spec}.?(c|m)[jt]s?(x)"],
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
