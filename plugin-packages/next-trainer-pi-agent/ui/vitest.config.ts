import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const uiRoot = fileURLToPath(new URL("./", import.meta.url));

export default defineConfig({
  root: uiRoot,
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup-dom.ts"],
    include: ["tests/**/*.dom.test.tsx"],
    clearMocks: true,
    restoreMocks: true,
  },
});
