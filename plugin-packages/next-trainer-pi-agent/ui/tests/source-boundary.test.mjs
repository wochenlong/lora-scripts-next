import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const sourceRoot = fileURLToPath(new URL("../src/", import.meta.url));

async function sourceEntries(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = join(directory, entry.name);
    if (entry.isDirectory()) return sourceEntries(target);
    return [target];
  }));
  return nested.flat();
}

test("the slim UI has no independent network or excluded project authority", async () => {
  const paths = (await sourceEntries(sourceRoot)).filter((path) => [".ts", ".tsx"].includes(extname(path)));
  const combined = (await Promise.all(paths.map((path) => readFile(path, "utf8")))).join("\n");
  const forbidden = [
    "fetch" + "(",
    "Event" + "Source",
    "Web" + "Socket",
    "XMLHttp" + "Request",
    "send" + "Beacon",
    "/" + "api/",
    "next" + "/server",
    "window" + ".open",
    "local" + "Storage",
    "session" + "Storage",
    "execute" + "Bash",
    "project" + "Trust",
    "work" + "tree",
  ];
  for (const token of forbidden) assert.equal(combined.includes(token), false, `forbidden source token: ${token}`);
});
