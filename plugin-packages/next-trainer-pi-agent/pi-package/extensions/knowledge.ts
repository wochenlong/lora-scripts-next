/**
 * Next Trainer knowledge & template library tool (pi extension).
 *
 * Serves the user-managed content in the plugin data root:
 *   - ``<dataRoot>/knowledge/**``   (Markdown knowledge documents)
 *   - ``<dataRoot>/templates/**``   (TOML training-parameter templates)
 *
 * The data root comes from ``NEXT_TRAINER_PLUGIN_DATA_ROOT`` (set by the host,
 * inherited by pi-web). This tool is the single, confined way the agent browses
 * that library:
 *   - ``list``   — relative paths + size + mtime, optionally narrowed by prefix
 *   - ``read``   — read one file by relative path
 *   - ``search`` — case-insensitive substring match over file names and bodies
 *
 * Frequent-update semantics (a product requirement): every action reads the
 * disk on demand — no cache, no index, no warm-up. Adding, editing or deleting
 * a file takes effect on the next tool call, with no restart, reinstall or
 * rebuild.
 *
 * Path confinement: every path is resolved and must stay inside the data root
 * AND under the ``knowledge/`` or ``templates/`` sub-root. Absolute paths,
 * ``..`` traversal and UNC paths are rejected, so the tool can never be used to
 * read launcher logs, pi session files or anything else in the data root.
 */
import path from "node:path";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const SEARCH_CAP = 50;
const READ_CAP = 200_000;
const CONTENT_SUBROOTS = ["knowledge", "templates"] as const;

interface FileEntry {
  path: string;
  size: number;
  mtimeMs: number;
}

interface SearchMatch {
  path: string;
  line: number;
  text: string;
}

function warn(message: string, ...rest: unknown[]): void {
  try {
    console.warn("[next-trainer:knowledge]", message, ...rest);
  } catch {
    /* diagnostics must never break extension loading */
  }
}

function dataRoot(): string | null {
  const raw = process.env.NEXT_TRAINER_PLUGIN_DATA_ROOT ?? "";
  if (!raw) return null;
  return path.resolve(raw);
}

/**
 * Resolve ``rel`` against ``root`` and return the absolute path only if it stays
 * inside ``root`` and under one of the content sub-roots. Otherwise null.
 */
function resolveContained(root: string, rel: string): string | null {
  if (!rel || typeof rel !== "string") return null;
  if (path.isAbsolute(rel) || rel.includes("\\\\")) return null; // absolute or UNC
  const normalized = rel.split("\\").join("/").replace(/^\/+/, "");
  const rootResolved = path.resolve(root);
  const resolved = path.resolve(rootResolved, normalized);
  if (resolved !== rootResolved && !resolved.startsWith(rootResolved + path.sep)) return null;
  const relToRoot = path.relative(rootResolved, resolved).split(path.sep).join("/");
  const underContent = CONTENT_SUBROOTS.some((sub) => relToRoot === sub || relToRoot.startsWith(sub + "/"));
  if (!underContent) return null;
  return resolved;
}

function collect(root: string): FileEntry[] {
  const out: FileEntry[] = [];
  const walk = (dir: string): void => {
    let entries: import("node:fs").Dirent[];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        const rel = path.relative(root, full).split(path.sep).join("/");
        let size = 0;
        let mtimeMs = 0;
        try {
          const st = statSync(full);
          size = st.size;
          mtimeMs = st.mtimeMs;
        } catch {
          /* stat races are non-fatal */
        }
        out.push({ path: rel, size, mtimeMs });
      }
    }
  };
  for (const sub of CONTENT_SUBROOTS) {
    const dir = path.join(root, sub);
    if (existsSync(dir)) walk(dir);
  }
  out.sort((a, b) => a.path.localeCompare(b.path));
  return out;
}

function search(root: string, query: string, prefix: string | undefined): SearchMatch[] {
  const q = query.toLowerCase();
  const out: SearchMatch[] = [];
  const push = (match: SearchMatch): boolean => {
    out.push(match);
    return out.length >= SEARCH_CAP;
  };
  for (const file of collect(root)) {
    if (prefix && !file.path.startsWith(prefix)) continue;
    if (file.path.toLowerCase().includes(q) && push({ path: file.path, line: 0, text: "(file name match)" })) return out;
    let content: string;
    try {
      content = readFileSync(path.join(root, file.path), "utf-8");
    } catch {
      continue;
    }
    const lines = content.split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      if (lines[i].toLowerCase().includes(q) && push({ path: file.path, line: i + 1, text: lines[i].trim().slice(0, 300) })) {
        return out;
      }
    }
  }
  return out;
}

function jsonResult(value: unknown): { content: Array<{ type: "text"; text: string }>; details: unknown } {
  return { content: [{ type: "text", text: JSON.stringify(value) }], details: null };
}

const Parameters = Type.Object({
  action: Type.Union([Type.Literal("list"), Type.Literal("read"), Type.Literal("search")]),
  path: Type.Optional(Type.String()),
  query: Type.Optional(Type.String()),
});

export default function nextTrainerKnowledge(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "next_trainer_knowledge",
    label: "Next Trainer knowledge",
    description:
      "Browse the Next Trainer knowledge base (Markdown) and training-parameter template library (TOML) in the plugin data root. " +
      "Use 'list' to see available files (optionally narrowed by a path prefix), 'read' to open one file by relative path " +
      "(e.g. 'knowledge/parameters/parameter-evidence-rules.md'), and 'search' for a case-insensitive substring match over file names and bodies. " +
      "Content is read from disk on every call, so newly added or edited files are available immediately.",
    promptSnippet: "List/read/search the Next Trainer knowledge (md) and template (toml) library.",
    parameters: Parameters,
    execute: async (_toolCallId, params) => {
      const root = dataRoot();
      if (!root) {
        return jsonResult({ error: "DATA_ROOT_MISSING", message: "NEXT_TRAINER_PLUGIN_DATA_ROOT is not set." });
      }

      if (params.action === "list") {
        let files = collect(root);
        if (params.path) files = files.filter((f) => f.path.startsWith(params.path as string));
        return jsonResult({ count: files.length, files });
      }

      if (params.action === "read") {
        const rel = params.path ?? "";
        const full = resolveContained(root, rel);
        if (!full) {
          return jsonResult({ error: "PATH_INVALID", message: "Path must be a relative path under knowledge/ or templates/." });
        }
        if (!existsSync(full) || !statSync(full).isFile()) {
          return jsonResult({ error: "NOT_FOUND", message: `No such file: ${rel}` });
        }
        let content = readFileSync(full, "utf-8");
        let truncated = false;
        if (content.length > READ_CAP) {
          content = content.slice(0, READ_CAP);
          truncated = true;
        }
        return jsonResult({ path: rel, truncated, content });
      }

      if (params.action === "search") {
        const query = params.query ?? "";
        if (!query.trim()) {
          return jsonResult({ error: "QUERY_REQUIRED", message: "search requires a non-empty 'query'." });
        }
        const matches = search(root, query, params.path);
        return jsonResult({ count: matches.length, truncated: matches.length >= SEARCH_CAP, matches });
      }

      return jsonResult({ error: "ACTION_INVALID", message: "action must be 'list', 'read' or 'search'." });
    },
  });
  warn("registered next_trainer_knowledge tool.");
}
