import { SidecarError } from "./errors.ts"
import type { ProviderRegistry } from "./pi/provider-registry.ts"

export interface ProviderFetchPolicy {
  restore(): void
}

function requestUrl(input: RequestInfo | URL): URL {
  if (input instanceof Request) return new URL(input.url)
  return new URL(String(input))
}

export function installProviderFetchPolicy(
  providers: ProviderRegistry,
  target: typeof globalThis = globalThis,
): ProviderFetchPolicy {
  const originalFetch = target.fetch.bind(target)
  const guardedFetch: typeof fetch = async (input, init) => {
    const url = requestUrl(input)
    const isChatCompletions = url.pathname.endsWith("/chat/completions")
    if (!isChatCompletions) return originalFetch(input, init)
    if (!providers.authorizesEndpoint(url)) {
      throw new SidecarError(403, "PROVIDER_ENDPOINT_NOT_AUTHORIZED", "Provider request endpoint is not authorized.")
    }
    const response = await originalFetch(input, { ...init, redirect: "manual" })
    if (response.status >= 300 && response.status < 400) {
      await response.body?.cancel().catch(() => undefined)
      throw new SidecarError(502, "PROVIDER_REDIRECT_BLOCKED", "Provider redirects are not allowed.")
    }
    return response
  }
  target.fetch = guardedFetch
  return {
    restore(): void {
      if (target.fetch === guardedFetch) target.fetch = originalFetch
    },
  }
}
