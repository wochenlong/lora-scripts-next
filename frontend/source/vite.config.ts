import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  build: {
    outDir: "../../build/frontend-source-dist",
    emptyOutDir: true,
    sourcemap: true,
  },
});
