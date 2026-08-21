import { readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)))
const lock = JSON.parse(await readFile(path.join(packageRoot, "package-lock.json"), "utf8"))

function packageName(packagePath, entry) {
  if (entry.name) return entry.name
  const marker = "node_modules/"
  const tail = packagePath.slice(packagePath.lastIndexOf(marker) + marker.length)
  const segments = tail.split("/")
  return tail.startsWith("@") ? `${segments[0]}/${segments[1]}` : segments[0]
}

function purlName(name) {
  return name.startsWith("@") ? `%40${name.slice(1).replace("/", "%2F")}` : encodeURIComponent(name)
}

const componentsByRef = new Map()
for (const [packagePath, entry] of Object.entries(lock.packages ?? {})) {
  if (!packagePath || !entry.version || !packagePath.includes("node_modules/")) continue
  const name = packageName(packagePath, entry)
  const installedManifest = path.join(packageRoot, packagePath, "package.json")
  let license
  try {
    const manifest = JSON.parse(await readFile(installedManifest, "utf8"))
    if (typeof manifest.license === "string") license = manifest.license
  } catch {
    // Lockfile identity remains authoritative when an optional package is not installed.
  }
  const purl = `pkg:npm/${purlName(name)}@${entry.version}`
  const component = {
    type: name === "bun" ? "framework" : "library",
    "bom-ref": purl,
    name,
    version: entry.version,
    purl,
    scope: entry.dev ? "excluded" : "required",
  }
  if (license) component.licenses = [{ license: { id: license } }]
  const previous = componentsByRef.get(purl)
  if (!previous || (previous.scope === "excluded" && component.scope === "required")) {
    componentsByRef.set(purl, component)
  }
}
const components = [...componentsByRef.values()]
components.sort((left, right) => left["bom-ref"].localeCompare(right["bom-ref"]))

const bom = {
  bomFormat: "CycloneDX",
  specVersion: "1.5",
  serialNumber: "urn:uuid:da389845-9cdd-4c08-a23c-364bd70fb7f7",
  version: 1,
  metadata: {
    component: {
      type: "application",
      "bom-ref": "pkg:npm/%40next-trainer%2Fpi-agent-plugin@0.1.0",
      name: "@next-trainer/pi-agent-plugin",
      version: "0.1.0",
    },
    properties: [
      { name: "next-trainer:source", value: "package-lock.json" },
      { name: "next-trainer:release-policy", value: "regenerate after every dependency change" },
    ],
  },
  components,
}

await writeFile(path.join(packageRoot, "sbom.cdx.json"), `${JSON.stringify(bom, null, 2)}\n`, "utf8")
process.stdout.write(`Generated SBOM with ${components.length} locked components.\n`)
