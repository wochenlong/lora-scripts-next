import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  server: {
    port: Number(process.env.VITE_PORT || 5173),
    strictPort: false,
    host: "127.0.0.1",
    proxy: {
      "/api": process.env.VITE_API_TARGET || "http://127.0.0.1:28000",
      "/proxy": process.env.VITE_API_TARGET || "http://127.0.0.1:28000",
      "/train-log": process.env.VITE_API_TARGET || "http://127.0.0.1:28000",
      "/train-monitor": process.env.VITE_API_TARGET || "http://127.0.0.1:28000",
      "/font-roboto": process.env.VITE_API_TARGET || "http://127.0.0.1:28000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
})
