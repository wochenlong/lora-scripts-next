import { defineConfig } from "vitest/config"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  test: {
    setupFiles: ["./vitest.setup.ts"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:28000",
      "/proxy": "http://127.0.0.1:28000",
      "/train-log": "http://127.0.0.1:28000",
      "/train-monitor": "http://127.0.0.1:28000",
      "/font-roboto": "http://127.0.0.1:28000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
})
