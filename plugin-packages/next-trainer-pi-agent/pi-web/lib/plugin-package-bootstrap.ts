/**
 * Next Trainer pi-package bootstrap.
 *
 * Registers the bundled Next Trainer pi package (host-Tool bridge extension,
 * knowledge/template tool, and the six skills) into the pi agent's user-scope
 * package settings so every pi-web session loads it — the same way a user would
 * install a package through the Plugins UI, and equally visible/manageable
 * there.
 *
 * Runs once per pi-web process (the promise is cached on globalThis, which
 * survives Next.js hot-reload). It is a no-op unless the launcher provided
 * ``NEXT_TRAINER_PI_PACKAGE_ROOT`` pointing at a valid pi package, so a plain
 * pi-web checkout with no Next Trainer package is untouched.
 *
 * Stale-entry handling: a plugin update moves the package to a new directory.
 * Any previous user-scope entry for the same package (matched by package name,
 * or by the gone ``pi-package`` directory) is removed before the current path is
 * registered, so exactly one entry is kept and the Plugins UI never accumulates
 * dead rows.
 *
 * Fail-safe: any error degrades to "package not registered this launch" and is
 * logged — it never throws into session startup.
 */
import { existsSync, readFileSync } from "fs";
import path from "path";
import {
  DefaultPackageManager,
  getAgentDir,
  SettingsManager,
  type PackageSource,
} from "@earendil-works/pi-coding-agent";

const PKG_NAME = "next-trainer-pi-assets";
const GLOBAL_KEY = "__nextTrainerPackageBootstrapPromise";

type GlobalWithBootstrap = typeof globalThis & {
  [GLOBAL_KEY]?: Promise<void>;
};

function warn(message: string, ...rest: unknown[]): void {
  try {
    console.warn("[next-trainer:bootstrap]", message, ...rest);
  } catch {
    /* diagnostics must never break startup */
  }
}

function resolvePiPackageRoot(): string | null {
  const raw = process.env.NEXT_TRAINER_PI_PACKAGE_ROOT;
  if (!raw) return null;
  const root = path.resolve(raw);
  const pkgJsonPath = path.join(root, "package.json");
  if (!existsSync(pkgJsonPath)) return null;
  try {
    const parsed = JSON.parse(readFileSync(pkgJsonPath, "utf-8")) as { pi?: unknown };
    if (!parsed || typeof parsed !== "object" || !parsed.pi) return null;
  } catch {
    return null;
  }
  return root;
}

function readPackageName(sourcePath: string): string | null {
  try {
    const parsed = JSON.parse(readFileSync(path.join(sourcePath, "package.json"), "utf-8")) as {
      name?: unknown;
    };
    return typeof parsed?.name === "string" ? parsed.name : null;
  } catch {
    return null;
  }
}

function sourceOf(entry: PackageSource): string {
  return typeof entry === "string" ? entry : entry.source;
}

/**
 * True when a user-scope entry is a stale Next Trainer package that should be
 * replaced by the current path. The stored source may be relative to the agent
 * dir (pi's portable form for local packages), so resolve it against agentDir
 * before comparing.
 */
function isOurStaleEntry(storedSource: string, currentRoot: string, agentDir: string): boolean {
  const resolvedStored = path.isAbsolute(storedSource)
    ? path.resolve(storedSource)
    : path.resolve(agentDir, storedSource);
  const resolvedCurrent = path.resolve(currentRoot);
  if (resolvedStored.toLowerCase() === resolvedCurrent.toLowerCase()) return false;
  if (existsSync(path.join(resolvedStored, "package.json"))) {
    return readPackageName(resolvedStored) === PKG_NAME;
  }
  // The old version directory was removed; treat a gone ``pi-package`` dir as ours.
  return path.basename(resolvedStored) === "pi-package";
}

async function installOnce(): Promise<void> {
  const root = resolvePiPackageRoot();
  if (!root) return; // not a Next Trainer deployment -> no-op
  const agentDir = getAgentDir();
  const cwd = process.cwd();
  const settingsManager = SettingsManager.create(cwd, agentDir);
  const packageManager = new DefaultPackageManager({ cwd, agentDir, settingsManager });

  // Drop stale Next Trainer entries (an older version path) by resolved
  // location. Editing the settings list directly (like the Plugins UI does for
  // enable/disable) avoids removeAndPersist's source-string matching, which is
  // brittle against pi's relative-to-agentDir storage form.
  const current = settingsManager.getGlobalSettings().packages ?? [];
  const next = current.filter((entry) => !isOurStaleEntry(sourceOf(entry), root, agentDir));
  if (next.length !== current.length) {
    settingsManager.setPackages(next);
    await settingsManager.flush();
  }

  await packageManager.installAndPersist(root, { local: false });
}

/**
 * Register the bundled Next Trainer pi package (once per process) and return a
 * promise that resolves when it is done. Always resolves — errors are logged,
 * never thrown.
 */
export function ensureNextTrainerPackage(): Promise<void> {
  const g = globalThis as GlobalWithBootstrap;
  if (g[GLOBAL_KEY]) return g[GLOBAL_KEY];
  const promise = installOnce().catch((error: unknown) => {
    warn(
      "failed to register pi package; continuing without it:",
      error instanceof Error ? error.message : String(error),
    );
  });
  g[GLOBAL_KEY] = promise;
  return promise;
}
