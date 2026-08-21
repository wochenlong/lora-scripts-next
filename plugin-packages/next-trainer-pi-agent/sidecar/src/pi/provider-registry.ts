import { randomUUID } from "node:crypto"
import { chmod, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises"
import path from "node:path"
import lockfile from "proper-lockfile"
import { fingerprintSecret } from "../auth.ts"
import type { ProviderProfileInput, ProviderStatus } from "../contracts.ts"
import { SidecarError } from "../errors.ts"

interface StoredProfileMetadata extends ProviderStatus {
  runtimeProviderId: string
}

interface ProviderFiles {
  auth: Record<string, { type: "api_key"; key: string }>
  models: {
    providers: Record<string, {
      name: string
      baseUrl: string
      api: "openai-completions"
      models: Array<{ id: string }>
    }>
  }
  profiles: Record<string, StoredProfileMetadata>
}

export interface ProviderBinding {
  profileId: string
  runtimeProviderId: string
  modelId: string
  endpoint: string
  baseUrl: string
}

export interface ProviderRegistryOptions {
  allowHttpLoopback?: boolean
}

export interface NormalizedEndpoint {
  authorizedEndpoint: string
  baseUrl: string
}

const PROFILE_ID = /^[a-z0-9][a-z0-9._-]{0,63}$/i

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function runtimeProviderId(profileId: string): string {
  return `next-trainer-${profileId.toLowerCase()}`
}

async function readJsonRecord(filePath: string): Promise<Record<string, unknown>> {
  try {
    const parsed: unknown = JSON.parse(await readFile(filePath, "utf8"))
    if (!isRecord(parsed)) throw new Error("JSON root is not an object")
    return parsed
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {}
    throw new SidecarError(500, "PROVIDER_STORAGE_INVALID", `Provider storage is invalid: ${path.basename(filePath)}.`)
  }
}

async function atomicWriteJson(filePath: string, value: unknown, mode: number): Promise<void> {
  const temporary = `${filePath}.${randomUUID()}.tmp`
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode })
  try {
    await rename(temporary, filePath)
  } catch (error) {
    if (process.platform !== "win32") throw error
    await rm(filePath, { force: true })
    await rename(temporary, filePath)
  } finally {
    await rm(temporary, { force: true })
  }
  await chmod(filePath, mode).catch(() => undefined)
}

export function normalizeChatCompletionsEndpoint(
  endpoint: string,
  options: { allowHttpLoopback?: boolean } = {},
): NormalizedEndpoint {
  let url: URL
  try {
    url = new URL(endpoint)
  } catch {
    throw new SidecarError(400, "PROVIDER_ENDPOINT_INVALID", "Provider endpoint must be an absolute URL.")
  }

  const httpLoopback = options.allowHttpLoopback === true && url.protocol === "http:" && url.hostname === "127.0.0.1"
  if (url.protocol !== "https:" && !httpLoopback) {
    throw new SidecarError(400, "PROVIDER_ENDPOINT_INVALID", "Provider endpoint must use HTTPS.")
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new SidecarError(400, "PROVIDER_ENDPOINT_INVALID", "Provider endpoint cannot contain credentials, query, or fragment.")
  }

  const pathname = url.pathname.replace(/\/+$/, "")
  const suffix = "/chat/completions"
  if (!pathname.endsWith(suffix)) {
    throw new SidecarError(400, "PROVIDER_ENDPOINT_INVALID", "Provider endpoint must end with /chat/completions.")
  }

  url.pathname = pathname
  const authorizedEndpoint = url.toString()
  url.pathname = pathname.slice(0, -suffix.length) || "/"
  const baseUrl = url.toString().replace(/\/$/, "")
  return { authorizedEndpoint, baseUrl }
}

export class ProviderRegistry {
  readonly #profiles = new Map<string, StoredProfileMetadata>()
  readonly #agentDir: string | null
  readonly #allowHttpLoopback: boolean

  constructor(agentDir: string | null = null, options: ProviderRegistryOptions = {}) {
    this.#agentDir = agentDir ? path.resolve(agentDir) : null
    this.#allowHttpLoopback = options.allowHttpLoopback === true
  }

  static async open(agentDir: string, options: ProviderRegistryOptions = {}): Promise<ProviderRegistry> {
    const registry = new ProviderRegistry(agentDir, options)
    await registry.#initialize()
    return registry
  }

  get agentDir(): string | null {
    return this.#agentDir
  }

  get authPath(): string | null {
    return this.#agentDir ? path.join(this.#agentDir, "auth.json") : null
  }

  get modelsPath(): string | null {
    return this.#agentDir ? path.join(this.#agentDir, "models.json") : null
  }

  async save(profileId: string, input: ProviderProfileInput): Promise<ProviderStatus> {
    this.#validate(profileId, input)
    const normalized = normalizeChatCompletionsEndpoint(input.endpoint, {
      allowHttpLoopback: this.#allowHttpLoopback,
    })
    const metadata: StoredProfileMetadata = {
      profileId,
      providerId: input.providerId.trim(),
      runtimeProviderId: runtimeProviderId(profileId),
      modelId: input.modelId.trim(),
      endpoint: normalized.authorizedEndpoint,
      baseUrl: normalized.baseUrl,
      configured: true,
      source: "plugin-auth",
      fingerprint: fingerprintSecret(input.apiKey),
      lastTest: null,
    }

    if (!this.#agentDir) {
      this.#profiles.set(profileId, metadata)
      return this.status(profileId)
    }

    await this.#withStorageLock(async () => {
      const files = await this.#readFiles()
      files.auth[metadata.runtimeProviderId] = { type: "api_key", key: input.apiKey }
      files.models.providers[metadata.runtimeProviderId] = {
        name: metadata.providerId,
        baseUrl: metadata.baseUrl,
        api: "openai-completions",
        models: [{ id: metadata.modelId }],
      }
      files.profiles[profileId] = metadata
      await this.#writeFiles(files)
    })
    this.#profiles.set(profileId, metadata)
    return this.status(profileId)
  }

  has(profileId: string): boolean {
    return this.#profiles.has(profileId)
  }

  defaultProfileId(): string | null {
    return [...this.#profiles.keys()].sort()[0] ?? null
  }

  status(profileId: string): ProviderStatus {
    const stored = this.#profiles.get(profileId)
    if (!stored) throw new SidecarError(404, "PROVIDER_PROFILE_NOT_FOUND", "Provider profile was not found.")
    const { runtimeProviderId: _runtimeProviderId, ...safeStatus } = stored
    return structuredClone(safeStatus)
  }

  binding(profileId: string): ProviderBinding {
    const stored = this.#profiles.get(profileId)
    if (!stored) throw new SidecarError(404, "PROVIDER_PROFILE_NOT_FOUND", "Provider profile was not found.")
    return {
      profileId,
      runtimeProviderId: stored.runtimeProviderId,
      modelId: stored.modelId,
      endpoint: stored.endpoint,
      baseUrl: stored.baseUrl,
    }
  }

  list(): ProviderStatus[] {
    return [...this.#profiles.keys()].sort().map((profileId) => this.status(profileId))
  }

  authorizesEndpoint(url: URL): boolean {
    if (url.username || url.password || url.search || url.hash) return false
    const candidate = url.toString().replace(/\/$/, "")
    return [...this.#profiles.values()].some((profile) => profile.endpoint === candidate)
  }

  async recordTest(profileId: string, ok: boolean): Promise<void> {
    const existing = this.#profiles.get(profileId)
    if (!existing) throw new SidecarError(404, "PROVIDER_PROFILE_NOT_FOUND", "Provider profile was not found.")
    const updated: StoredProfileMetadata = {
      ...existing,
      lastTest: { ok, testedAt: new Date().toISOString() },
    }
    if (this.#agentDir) {
      await this.#withStorageLock(async () => {
        const files = await this.#readFiles()
        files.profiles[profileId] = updated
        await atomicWriteJson(path.join(this.#agentDir!, "provider-profiles.json"), { profiles: files.profiles }, 0o600)
      })
    }
    this.#profiles.set(profileId, updated)
  }

  async remove(profileId: string): Promise<boolean> {
    const existing = this.#profiles.get(profileId)
    if (!existing) return false
    if (this.#agentDir) {
      await this.#withStorageLock(async () => {
        const files = await this.#readFiles()
        delete files.auth[existing.runtimeProviderId]
        delete files.models.providers[existing.runtimeProviderId]
        delete files.profiles[profileId]
        await this.#writeFiles(files)
      })
    }
    return this.#profiles.delete(profileId)
  }

  async #initialize(): Promise<void> {
    if (!this.#agentDir) return
    await mkdir(this.#agentDir, { recursive: true, mode: 0o700 })
    await chmod(this.#agentDir, 0o700).catch(() => undefined)
    const files = await this.#readFiles()
    for (const [profileId, raw] of Object.entries(files.profiles)) {
      if (!PROFILE_ID.test(profileId) || !isRecord(raw)) continue
      const metadata = raw as unknown as StoredProfileMetadata
      const credential = files.auth[metadata.runtimeProviderId]
      const model = files.models.providers[metadata.runtimeProviderId]
      if (!credential?.key || !model || metadata.configured !== true) continue
      this.#profiles.set(profileId, structuredClone(metadata))
    }
  }

  #validate(profileId: string, input: ProviderProfileInput): void {
    if (!PROFILE_ID.test(profileId)) {
      throw new SidecarError(400, "PROVIDER_PROFILE_INVALID", "Provider profile ID is invalid.")
    }
    if (!input.providerId.trim() || !input.modelId.trim() || !input.apiKey) {
      throw new SidecarError(400, "PROVIDER_PROFILE_INVALID", "Provider, model, endpoint, and API key are required.")
    }
  }

  async #withStorageLock<T>(operation: () => Promise<T>): Promise<T> {
    if (!this.#agentDir) return operation()
    const release = await lockfile.lock(this.#agentDir, {
      realpath: false,
      retries: { retries: 20, factor: 1.2, minTimeout: 10, maxTimeout: 100 },
      stale: 10_000,
    })
    try {
      return await operation()
    } finally {
      await release()
    }
  }

  async #readFiles(): Promise<ProviderFiles> {
    if (!this.#agentDir) return { auth: {}, models: { providers: {} }, profiles: {} }
    const authRoot = await readJsonRecord(path.join(this.#agentDir, "auth.json"))
    const modelsRoot = await readJsonRecord(path.join(this.#agentDir, "models.json"))
    const profilesRoot = await readJsonRecord(path.join(this.#agentDir, "provider-profiles.json"))
    const auth = authRoot as ProviderFiles["auth"]
    const providers = isRecord(modelsRoot.providers)
      ? modelsRoot.providers as ProviderFiles["models"]["providers"]
      : {}
    const profiles = isRecord(profilesRoot.profiles)
      ? profilesRoot.profiles as unknown as ProviderFiles["profiles"]
      : {}
    return { auth, models: { providers }, profiles }
  }

  async #writeFiles(files: ProviderFiles): Promise<void> {
    if (!this.#agentDir) return
    await atomicWriteJson(path.join(this.#agentDir, "auth.json"), files.auth, 0o600)
    await atomicWriteJson(path.join(this.#agentDir, "models.json"), files.models, 0o600)
    await atomicWriteJson(path.join(this.#agentDir, "provider-profiles.json"), { profiles: files.profiles }, 0o600)
  }
}
