import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The `@/*` alias is declared by hand rather than read from tsconfig.json via
// vite-tsconfig-paths. That package is ESM-only, and vitest bundles this config
// with esbuild in CJS mode, so importing it fails at startup with
// "ESM file cannot be loaded by require". One alias is not worth a dependency
// that cannot be loaded.
const src = fileURLToPath(new URL("./src", import.meta.url));

// Tests live in `tests/`, mirroring `backend/tests/`, rather than beside the
// source. Files under `src/` are compiled by `next build`, and test files there
// would be type-checked and bundled as part of the shipped app.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": src },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    // Every mock is undone between tests; a leaked fetch stub is otherwise very
    // hard to trace back to the test that set it.
    restoreMocks: true,
    clearMocks: true,
  },
});
