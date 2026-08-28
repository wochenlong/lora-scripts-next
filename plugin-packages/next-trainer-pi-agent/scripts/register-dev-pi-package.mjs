#!/usr/bin/env node
/**
 * Dev utility: register the Next Trainer pi package into the dev agent dir's pi
 * settings so the dev server's Plugins/Skills UI shows it immediately — without
 * waiting for the first chat session to trigger the in-process bootstrap.
 *
 * It runs the SAME code as pi-web/lib/plugin-package-bootstrap.ts (loaded through
 * jiti with the same typebox/SDK aliasing pi uses), so the result is identical
 * and the in-process bootstrap later sees the package already installed and is a
 * no-op (idempotent).
 *
 * By default it targets the shared installed-plugin agent dir (the same dir the
 * dev server uses) and the working-tree pi-package. Override with flags:
 *
 *   node scripts/register-dev-pi-package.mjs [--agent-dir <dir>] [--package-root <dir>]
 *
 * Run with the project Node runtime (from project/):
 *   E:\OpenSourceTeamWork\.dev-runtimes\node-v22.19.0\node.exe \
 *     plugin-packages\next-trainer-pi-agent\scripts\register-dev-pi-package.mjs
 */
import { createRequire } from "node:module";
import path from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.resolve(here, "..");
const piWebRoot = path.join(pkgRoot, "pi-web");
const projectRoot = path.resolve(pkgRoot, "..", "..");

function argValue(flag, fallback) {
  const i = process.argv.indexOf(flag);
  if (i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--")) return process.argv[i + 1];
  return fallback;
}

const agentDir = path.resolve(
  argValue("--agent-dir", path.join(projectRoot, ".runtime", "plugin-marketplace", "data", "next-trainer-pi-agent", "pi-agent")),
);
const packageRoot = path.resolve(argValue("--package-root", path.join(pkgRoot, "pi-package")));

const pkgJson = path.join(packageRoot, "package.json");
if (!existsSync(pkgJson)) {
  console.error(`[register-dev] pi package root missing package.json: ${packageRoot}`);
  process.exit(1);
}

// The bootstrap reads these at call time (getAgentDir() honours PI_CODING_AGENT_DIR).
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.NEXT_TRAINER_PI_PACKAGE_ROOT = packageRoot;

const requireFromPiWeb = createRequire(path.join(piWebRoot, "package.json"));
const { createJiti } = requireFromPiWeb("jiti");
const typeboxAlias = requireFromPiWeb.resolve("typebox");
const sdkAlias = path.join(piWebRoot, "node_modules/@earendil-works/pi-coding-agent/dist/index.js");
const jiti = createJiti(import.meta.url, {
  alias: { typebox: typeboxAlias, "@earendil-works/pi-coding-agent": sdkAlias },
});

// Run with cwd = pi-web so SettingsManager's scope resolution matches the dev server.
process.chdir(piWebRoot);
const mod = await jiti.import(path.join(piWebRoot, "lib", "plugin-package-bootstrap.ts"));
await mod.ensureNextTrainerPackage();

const settingsPath = path.join(agentDir, "settings.json");
if (existsSync(settingsPath)) {
  const parsed = JSON.parse(readFileSync(settingsPath, "utf-8"));
  const ours = (parsed.packages ?? []).filter((e) => JSON.stringify(e).includes("next-trainer-pi-assets") || JSON.stringify(e).includes("pi-package"));
  console.log(`[register-dev] agent dir: ${agentDir}`);
  console.log(`[register-dev] package root: ${packageRoot}`);
  console.log(`[register-dev] user-scope Next Trainer entries:`);
  console.log(JSON.stringify(ours, null, 2));
  if (ours.length === 0) {
    console.error("[register-dev] WARNING: no Next Trainer package entry found after bootstrap.");
    process.exit(2);
  }
} else {
  console.error(`[register-dev] WARNING: settings.json not found at ${settingsPath}`);
  process.exit(3);
}
console.log("[register-dev] done.");
