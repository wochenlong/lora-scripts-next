import { copyFile, mkdir } from "node:fs/promises"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)))
const outputDir = path.join(packageRoot, "dist", "ui")
await mkdir(outputDir, { recursive: true })

const bunPath = process.platform === "win32"
  ? path.join(packageRoot, "node_modules", "@oven", "bun-windows-x64", "bin", "bun.exe")
  : path.join(packageRoot, "node_modules", ".bin", "bun")
const result = spawnSync(
  bunPath,
  [
    "build",
    "ui/src/main.tsx",
    "--target=browser",
    "--minify",
    "--outdir=dist/ui",
    "--entry-naming=index.[ext]",
  ],
  { cwd: packageRoot, stdio: "inherit" },
)

if (result.error) throw result.error
if (result.status !== 0) process.exit(result.status ?? 1)
await copyFile(path.join(packageRoot, "ui", "index.html"), path.join(outputDir, "index.html"))
await copyFile(path.join(packageRoot, "ui", "settings.html"), path.join(outputDir, "settings.html"))
