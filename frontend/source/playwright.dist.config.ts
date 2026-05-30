import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 30_000,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4183",
  },
  webServer: {
    command: "node scripts/serve-static-dist.mjs ../../frontend/dist 4183",
    url: "http://127.0.0.1:4183",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
