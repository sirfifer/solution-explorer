import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import pkg from "./package.json" with { type: "json" };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: process.env.VITE_BASE_URL || "./",
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    // Build-time maturity gate (card R3). Genuinely-unfinished code guarded by
    // `if (__EXPERIMENTAL_BUILD__)` is dead-code-eliminated from a production
    // build (the default: false). An experimental build sets
    // VITE_EXPERIMENTAL_BUILD=1 to include that code.
    __EXPERIMENTAL_BUILD__: JSON.stringify(
      process.env.VITE_EXPERIMENTAL_BUILD === "1" ||
        process.env.VITE_EXPERIMENTAL_BUILD === "true",
    ),
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
