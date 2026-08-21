import { createHash, timingSafeEqual } from "node:crypto"
import { SidecarError } from "./errors.ts"

function digest(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest()
}

export function secretsEqual(actual: string, expected: string): boolean {
  return timingSafeEqual(digest(actual), digest(expected))
}

export function requireBearer(request: Request, expectedToken: string): void {
  const authorization = request.headers.get("authorization")
  const match = authorization ? /^Bearer\s+(\S+)$/i.exec(authorization) : null
  if (!match || !secretsEqual(match[1] ?? "", expectedToken)) {
    throw new SidecarError(401, "SIDECAR_AUTH_REQUIRED", "A valid sidecar bearer credential is required.")
  }
}

export function fingerprintSecret(secret: string): string {
  return createHash("sha256").update(secret, "utf8").digest("hex").slice(0, 12)
}

const SECRET_FIELD = /(?:api[-_]?key|authorization|token|secret|password)/i

export function redactForDiagnostics(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactForDiagnostics)
  if (!value || typeof value !== "object") return value

  return Object.fromEntries(
    Object.entries(value).map(([key, entry]) => [
      key,
      SECRET_FIELD.test(key) ? "[REDACTED]" : redactForDiagnostics(entry),
    ]),
  )
}
