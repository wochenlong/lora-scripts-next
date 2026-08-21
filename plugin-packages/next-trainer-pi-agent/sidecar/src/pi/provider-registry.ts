import { fingerprintSecret } from "../auth.ts"
import type { ProviderProfileInput, ProviderStatus } from "../contracts.ts"
import { SidecarError } from "../errors.ts"

interface StoredProfile extends ProviderStatus {
  apiKey: string
}

export interface NormalizedEndpoint {
  authorizedEndpoint: string
  baseUrl: string
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
  readonly #profiles = new Map<string, StoredProfile>()

  save(profileId: string, input: ProviderProfileInput): ProviderStatus {
    if (!/^[a-z0-9][a-z0-9._-]{0,63}$/i.test(profileId)) {
      throw new SidecarError(400, "PROVIDER_PROFILE_INVALID", "Provider profile ID is invalid.")
    }
    if (!input.providerId.trim() || !input.modelId.trim() || !input.apiKey) {
      throw new SidecarError(400, "PROVIDER_PROFILE_INVALID", "Provider, model, endpoint, and API key are required.")
    }

    const normalized = normalizeChatCompletionsEndpoint(input.endpoint)
    const stored: StoredProfile = {
      profileId,
      providerId: input.providerId.trim(),
      modelId: input.modelId.trim(),
      endpoint: normalized.authorizedEndpoint,
      baseUrl: normalized.baseUrl,
      configured: true,
      source: "plugin-auth",
      fingerprint: fingerprintSecret(input.apiKey),
      lastTest: null,
      apiKey: input.apiKey,
    }
    this.#profiles.set(profileId, stored)
    return this.status(profileId)
  }

  has(profileId: string): boolean {
    return this.#profiles.has(profileId)
  }

  status(profileId: string): ProviderStatus {
    const stored = this.#profiles.get(profileId)
    if (!stored) throw new SidecarError(404, "PROVIDER_PROFILE_NOT_FOUND", "Provider profile was not found.")
    const { apiKey: _apiKey, ...safeStatus } = stored
    return structuredClone(safeStatus)
  }

  list(): ProviderStatus[] {
    return [...this.#profiles.keys()].sort().map((profileId) => this.status(profileId))
  }

  remove(profileId: string): boolean {
    return this.#profiles.delete(profileId)
  }
}
