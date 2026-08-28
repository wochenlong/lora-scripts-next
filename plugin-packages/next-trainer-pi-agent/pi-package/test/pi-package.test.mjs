/**
 * P2 verification for the Next Trainer pi package.
 *
 * Loads the real extension modules through jiti with the same aliasing pi uses
 * (typebox + the pi SDK resolve to pi-web's copies), so the modules are parsed,
 * type-stripped and their imports resolved exactly the way the pi runtime will
 * do. It then exercises:
 *
 *   - knowledge.ts  : list / read / search + path confinement (no `..`, no
 *                     absolute/UNC paths, nothing outside knowledge|templates)
 *   - host-tools.ts : catalog fetch, per-tool registration, reserved/invalid
 *                     name skipping, execute headers (session + tool-call id),
 *                     and fail-closed behaviour (no creds / unreachable gateway)
 *   - bootstrap.ts  : no-op without env, install, idempotency, and stale-path
 *                     replacement (exactly one user-scope entry)
 *
 * Run with the project Node runtime:
 *   node plugin-packages/next-trainer-pi-agent/pi-package/test/pi-package.test.mjs
 */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const piWebRoot = path.resolve(here, "../../pi-web");
const requireFromPiWeb = createRequire(path.join(piWebRoot, "package.json"));
const { createJiti } = requireFromPiWeb("jiti");

const typeboxAlias = requireFromPiWeb.resolve("typebox");
// Point the SDK alias at the same entry pi's own loader uses (dist/index.js);
// require.resolve of the package root is blocked by its "exports" map.
const sdkAlias = path.join(piWebRoot, "node_modules/@earendil-works/pi-coding-agent/dist/index.js");

function makeLoader() {
  return createJiti(import.meta.url, {
    alias: {
      typebox: typeboxAlias,
      "@earendil-works/pi-coding-agent": sdkAlias,
    },
  });
}

function makeMockPi() {
  const tools = [];
  return {
    tools,
    api: {
      registerTool: (def) => {
        tools.push(def);
      },
    },
  };
}

function parseText(result) {
  return JSON.parse(result.content[0].text);
}

let tmpDirs = [];
function makeTmpDir(prefix) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  tmpDirs.push(dir);
  return dir;
}

after(() => {
  for (const dir of tmpDirs) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// knowledge.ts
// ---------------------------------------------------------------------------
test("knowledge tool: list / read / search + confinement", async (t) => {
  const dataRoot = makeTmpDir("nt-knowledge-");
  fs.mkdirSync(path.join(dataRoot, "knowledge", "parameters"), { recursive: true });
  fs.mkdirSync(path.join(dataRoot, "knowledge", "model-families"), { recursive: true });
  fs.mkdirSync(path.join(dataRoot, "templates"), { recursive: true });
  fs.mkdirSync(path.join(dataRoot, "secret"), { recursive: true });
  fs.writeFileSync(
    path.join(dataRoot, "knowledge", "parameters", "parameter-evidence-rules.md"),
    "# Parameter evidence rules\n\nSeparate learning rate layers.\n",
    "utf-8",
  );
  fs.writeFileSync(
    path.join(dataRoot, "knowledge", "model-families", "sd15-lora-parameter-baseline.md"),
    "# SD 1.5 baseline\n",
    "utf-8",
  );
  fs.writeFileSync(path.join(dataRoot, "templates", "sd15-lora-conservative.toml"), "network_dim = 16\n", "utf-8");
  fs.writeFileSync(path.join(dataRoot, "secret", "nope.txt"), "top secret\n", "utf-8");
  fs.writeFileSync(path.join(dataRoot, "root.txt"), "root level\n", "utf-8");

  const prev = process.env.NEXT_TRAINER_PLUGIN_DATA_ROOT;
  process.env.NEXT_TRAINER_PLUGIN_DATA_ROOT = dataRoot;
  t.after(() => {
    if (prev === undefined) delete process.env.NEXT_TRAINER_PLUGIN_DATA_ROOT;
    else process.env.NEXT_TRAINER_PLUGIN_DATA_ROOT = prev;
  });

  const loader = makeLoader();
  const mod = await loader.import(path.join(here, "../extensions/knowledge.ts"), { default: true });
  const mock = makeMockPi();
  mod(mock.api);

  assert.equal(mock.tools.length, 1, "registers exactly one tool");
  const tool = mock.tools[0];
  assert.equal(tool.name, "next_trainer_knowledge");

  // list: only knowledge/ and templates/ are exposed.
  const list = parseText(await tool.execute("tc-list", { action: "list" }, undefined, undefined, {}));
  const paths = list.files.map((f) => f.path);
  assert.ok(paths.includes("knowledge/parameters/parameter-evidence-rules.md"));
  assert.ok(paths.includes("templates/sd15-lora-conservative.toml"));
  assert.ok(!paths.some((p) => p.startsWith("secret/")), "secret/ is not exposed");
  assert.ok(!paths.includes("root.txt"), "root-level file is not exposed");

  // read: a valid knowledge file.
  const read = parseText(
    await tool.execute("tc-read", { action: "read", path: "knowledge/parameters/parameter-evidence-rules.md" }, undefined, undefined, {}),
  );
  assert.match(read.content, /learning rate layers/);

  // read: the template.
  const readT = parseText(await tool.execute("tc-readt", { action: "read", path: "templates/sd15-lora-conservative.toml" }, undefined, undefined, {}));
  assert.match(readT.content, /network_dim = 16/);

  // confinement: outside the content sub-roots, traversal, and absolute paths are rejected.
  for (const evil of [
    { action: "read", path: "secret/nope.txt" },
    { action: "read", path: "root.txt" },
    { action: "read", path: "../escape.txt" },
    { action: "read", path: "knowledge/../../secret/nope.txt" },
    { action: "read", path: "/etc/passwd" },
    { action: "read", path: "C:\\Windows\\system.ini" },
    { action: "read", path: "\\\\server\\share\\file.txt" },
  ]) {
    const res = parseText(await tool.execute("tc-evil", evil, undefined, undefined, {}));
    assert.ok(res.error, `expected an error for ${JSON.stringify(evil.path)} but got ${res.error ?? "none"}`);
  }

  // search: finds a body match; empty query is rejected.
  const found = parseText(await tool.execute("tc-search", { action: "search", query: "learning rate" }, undefined, undefined, {}));
  assert.ok(found.count >= 1, "search finds the seeded phrase");
  assert.ok(found.matches.some((m) => m.path === "knowledge/parameters/parameter-evidence-rules.md" && m.line >= 1));
  const emptyQ = parseText(await tool.execute("tc-search2", { action: "search", query: "   " }, undefined, undefined, {}));
  assert.equal(emptyQ.error, "QUERY_REQUIRED");
});

// ---------------------------------------------------------------------------
// host-tools.ts
// ---------------------------------------------------------------------------
test("host tools: catalog, registration, execute headers, fail-closed", async (t) => {
  const seen = [];
  const gateway = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const body = Buffer.concat(chunks).toString("utf-8");
      if (req.method === "GET" && req.url === "/internal/agent-tools/definitions") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            ok: true,
            data: {
              tools: [
                { name: "training_config_validate", label: "Validate", description: "Validate a config", parameters: { type: "object", properties: { draft: { type: "string" } } } },
                { name: "tagger_status", label: "Tagger status", description: "Status", parameters: { type: "object", properties: {} } },
                { name: "read", label: "Reserved", description: "reserved name", parameters: { type: "object" } },
                { name: "Bad-Name", label: "Invalid", description: "invalid name", parameters: { type: "object" } },
              ],
            },
          }),
        );
        return;
      }
      const match = req.url && req.url.match(/^\/internal\/agent-tools\/(.+)$/);
      if (req.method === "POST" && match) {
        seen.push({ tool: decodeURIComponent(match[1]), headers: req.headers, body });
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true, data: { echoed: true, tool: decodeURIComponent(match[1]) }, audit_id: "audit-1", details: { via: "gateway" } }));
        return;
      }
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: { code: "NOT_FOUND", message: "no route" } }));
    });
  });
  await new Promise((resolve) => gateway.listen(0, "127.0.0.1", resolve));
  const port = gateway.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;
  const token = "test-token-0123456789-0123456789-0123"; // > 32 chars

  const prevUrl = process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL;
  const prevToken = process.env.NEXT_TRAINER_HOST_TOOL_TOKEN;
  process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL = baseUrl;
  process.env.NEXT_TRAINER_HOST_TOOL_TOKEN = token;
  t.after(() => {
    gateway.close();
    if (prevUrl === undefined) delete process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL;
    else process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL = prevUrl;
    if (prevToken === undefined) delete process.env.NEXT_TRAINER_HOST_TOOL_TOKEN;
    else process.env.NEXT_TRAINER_HOST_TOOL_TOKEN = prevToken;
  });

  const loader = makeLoader();
  const mod = await loader.import(path.join(here, "../extensions/host-tools.ts"), { default: true });

  // happy path
  const mock = makeMockPi();
  await mod(mock.api);
  const names = mock.tools.map((t) => t.name).sort();
  assert.deepEqual(names, ["tagger_status", "training_config_validate"], "reserved + invalid names are skipped");

  const validateTool = mock.tools.find((t) => t.name === "training_config_validate");
  const ctx = { sessionManager: { getSessionId: () => "sess-1" } };
  const result = await validateTool.execute("tc-1", { draft: "x" }, undefined, undefined, ctx);
  assert.equal(seen.length, 1, "one gateway call");
  assert.equal(seen[0].tool, "training_config_validate");
  assert.equal(seen[0].headers.authorization, `Bearer ${token}`);
  assert.equal(seen[0].headers["x-next-trainer-session-id"], "sess-1");
  assert.equal(seen[0].headers["x-next-trainer-tool-call-id"], "tc-1");
  assert.deepEqual(JSON.parse(seen[0].body), { arguments: { draft: "x" } });
  const payload = parseText(result);
  assert.equal(payload.echoed, true);
  assert.equal(result.details.auditId, "audit-1");

  // fail-closed: no credentials -> nothing registered, no throw
  const mockNoCreds = makeMockPi();
  const savedUrl = process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL;
  const savedToken = process.env.NEXT_TRAINER_HOST_TOOL_TOKEN;
  delete process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL;
  delete process.env.NEXT_TRAINER_HOST_TOOL_TOKEN;
  await mod(mockNoCreds.api);
  assert.equal(mockNoCreds.tools.length, 0, "no tools without credentials");
  process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL = savedUrl;
  process.env.NEXT_TRAINER_HOST_TOOL_TOKEN = savedToken;

  // fail-closed: unreachable gateway -> nothing registered, no throw
  process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL = "http://127.0.0.1:1"; // port 1: refused
  const mockUnreachable = makeMockPi();
  await mod(mockUnreachable.api);
  assert.equal(mockUnreachable.tools.length, 0, "no tools when the gateway is unreachable");
  process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL = baseUrl;
});

// ---------------------------------------------------------------------------
// bootstrap (pi-web/lib/plugin-package-bootstrap.ts)
// ---------------------------------------------------------------------------
test("bootstrap: no-op, install, idempotent, stale replacement", async (t) => {
  const loader = makeLoader();
  const boot = await loader.import(path.join(piWebRoot, "lib/plugin-package-bootstrap.ts"), { default: false });
  const { ensureNextTrainerPackage } = boot;

  const GLOBAL_KEY = "__nextTrainerPackageBootstrapPromise";
  const clearCache = () => {
    delete globalThis[GLOBAL_KEY];
  };

  function makeFakePkg(parent, sub) {
    const dir = path.join(parent, sub);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "package.json"),
      JSON.stringify({ name: "next-trainer-pi-assets", version: "0.3.0", pi: { extensions: ["./extensions"], skills: ["./skills"] } }),
      "utf-8",
    );
    return dir;
  }

  // pi stores local package sources relative to the agent dir; resolve them back
  // to absolute (case-folded) paths so we can compare against the real pkg dirs.
  function readResolvedPackages(agentDir) {
    const p = path.join(agentDir, "settings.json");
    if (!fs.existsSync(p)) return [];
    const parsed = JSON.parse(fs.readFileSync(p, "utf-8"));
    return (parsed.packages ?? [])
      .map((s) => (typeof s === "string" ? s : s.source))
      .map((s) => (path.isAbsolute(s) ? path.resolve(s) : path.resolve(agentDir, s)).toLowerCase());
  }

  const prevAgentDir = process.env.PI_CODING_AGENT_DIR;
  const prevPkgRoot = process.env.NEXT_TRAINER_PI_PACKAGE_ROOT;
  t.after(() => {
    clearCache();
    if (prevAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = prevAgentDir;
    if (prevPkgRoot === undefined) delete process.env.NEXT_TRAINER_PI_PACKAGE_ROOT;
    else process.env.NEXT_TRAINER_PI_PACKAGE_ROOT = prevPkgRoot;
  });

  // A. no env -> no-op (a fresh agentDir stays empty of packages)
  const agentDirA = makeTmpDir("nt-boot-A-");
  process.env.PI_CODING_AGENT_DIR = agentDirA;
  delete process.env.NEXT_TRAINER_PI_PACKAGE_ROOT;
  clearCache();
  await ensureNextTrainerPackage();
  assert.deepEqual(readResolvedPackages(agentDirA), [], "no package registered without NEXT_TRAINER_PI_PACKAGE_ROOT");

  // B + C + D share one agentDir
  const agentDirB = makeTmpDir("nt-boot-B-");
  process.env.PI_CODING_AGENT_DIR = agentDirB;
  const pkg1 = makeFakePkg(makeTmpDir("nt-pkg1-"), "pi-package");
  const pkg2 = makeFakePkg(makeTmpDir("nt-pkg2-"), "pi-package");

  process.env.NEXT_TRAINER_PI_PACKAGE_ROOT = pkg1;
  clearCache();
  await ensureNextTrainerPackage();
  assert.deepEqual(readResolvedPackages(agentDirB), [pkg1.toLowerCase()], "first install registers the package");

  // C. idempotent second call -> still exactly one entry
  clearCache();
  await ensureNextTrainerPackage();
  assert.deepEqual(readResolvedPackages(agentDirB), [pkg1.toLowerCase()], "re-install is idempotent");

  // D. stale replacement: point at a different path for the same package
  process.env.NEXT_TRAINER_PI_PACKAGE_ROOT = pkg2;
  clearCache();
  await ensureNextTrainerPackage();
  assert.deepEqual(readResolvedPackages(agentDirB), [pkg2.toLowerCase()], "stale path is replaced; exactly one entry");
});
