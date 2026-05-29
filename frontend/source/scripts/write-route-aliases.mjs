import { copyFile, mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const sourceRoot = resolve(import.meta.dirname, "..");
const outDir = resolve(sourceRoot, "../../build/frontend-source-dist");
const routes = JSON.parse(await readFile(resolve(sourceRoot, "src/routes.json"), "utf8"));
const indexPath = resolve(outDir, "index.html");

for (const route of routes) {
  if (route.path === "/") continue;
  const target = resolve(outDir, route.path.slice(1));
  await mkdir(dirname(target), { recursive: true });
  await copyFile(indexPath, target);
}

console.log(`wrote ${routes.length - 1} route aliases`);
