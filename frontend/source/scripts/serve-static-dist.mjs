import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const [rootArg = "../../frontend/dist", portArg = "4183"] = process.argv.slice(2);
const root = resolve(rootArg);
const port = Number(portArg);

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
]);

function resolveRequestPath(url = "/") {
  const pathname = decodeURIComponent(new URL(url, "http://127.0.0.1").pathname);
  const normalized = normalize(pathname).replace(/^([/\\])+/, "");
  const candidate = resolve(join(root, normalized || "index.html"));
  if (candidate !== root && !candidate.startsWith(`${root}${sep}`)) {
    return null;
  }
  if (existsSync(candidate) && statSync(candidate).isFile()) {
    return candidate;
  }
  return resolve(join(root, "index.html"));
}

createServer((request, response) => {
  const file = resolveRequestPath(request.url);
  if (!file || !existsSync(file)) {
    response.writeHead(404);
    response.end("not found");
    return;
  }
  response.writeHead(200, {
    "content-type": contentTypes.get(extname(file)) || "application/octet-stream",
    "cache-control": "no-cache",
  });
  createReadStream(file).pipe(response);
}).listen(port, "127.0.0.1", () => {
  console.log(`serving ${root} at http://127.0.0.1:${port}`);
});
