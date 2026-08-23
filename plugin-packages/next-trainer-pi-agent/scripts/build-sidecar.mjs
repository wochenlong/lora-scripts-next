import { mkdir } from "node:fs/promises"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)))
const outputDir = path.join(packageRoot, "dist", "bin")
await mkdir(outputDir, { recursive: true })

const bunPath = process.platform === "win32"
  ? path.join(packageRoot, "node_modules", "@oven", "bun-windows-x64", "bin", "bun.exe")
  : path.join(packageRoot, "node_modules", ".bin", "bun")
const result = spawnSync(
  bunPath,
  [
    "build",
    "sidecar/src/main.ts",
    "--compile",
    "--target=bun-windows-x64-baseline",
    "--outfile=dist/bin/next-trainer-pi-agent.exe",
  ],
  { cwd: packageRoot, stdio: "inherit" },
)

if (result.error) throw result.error
process.exitCode = result.status ?? 1
