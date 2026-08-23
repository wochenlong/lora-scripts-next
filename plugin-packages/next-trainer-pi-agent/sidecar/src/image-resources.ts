/**
 * Safe image resource resolution for VLM prompt attachments.
 *
 * Image resources are confined to the plugin data root: absolute paths, UNC
 * paths, traversal, symlinks and reparse points are rejected, media types are
 * allowlisted, payloads are size-capped and magic-byte checked so a crafted
 * resourceId can never read host files or smuggle non-image bytes into the
 * model context.
 */
import { lstat, readFile } from "node:fs/promises"
import path from "node:path"
import { SidecarError } from "./errors.ts"

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024

const IMAGE_MIME_TYPES = new Set(["image/png", "image/jpeg", "image/webp"])

const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47]
const JPEG_MAGIC = [0xff, 0xd8, 0xff]
const WEBP_MAGIC = [0x52, 0x49, 0x46, 0x46, 0x00, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50]

function startsWith(bytes: Uint8Array, magic: number[]): boolean {
  if (bytes.length < magic.length) return false
  return magic.every((value, index) => bytes[index] === value)
}

export interface ResolvedImage {
  type: "image"
  data: string
  mimeType: string
}

/** Reject if the entry is a symlink or a Windows reparse point. */
async function assertNotReparse(candidate: string): Promise<void> {
  const info = await lstat(candidate)
  if (info.isSymbolicLink()) {
    throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
  }
  const attributes = (info as unknown as { st_file_attributes?: number }).st_file_attributes
  if (typeof attributes === "number" && (attributes & 0x400) !== 0) {
    throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
  }
}

function checkPayload(data: Uint8Array, mediaType: string): void {
  if (data.length > MAX_IMAGE_BYTES) {
    throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
  }
  const magic = mediaType === "image/png" ? PNG_MAGIC : mediaType === "image/jpeg" ? JPEG_MAGIC : WEBP_MAGIC
  if (!startsWith(data, magic)) {
    throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
  }
}

/** Validate an inline base64 image payload supplied by the host. */
export function decodeInlineImage(data: string, mediaType: string): Uint8Array {
  const unavailable = () => new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
  if (!IMAGE_MIME_TYPES.has(mediaType)) throw unavailable()
  if (typeof data !== "string" || data.length === 0) throw unavailable()
  const bytes = Uint8Array.from(Buffer.from(data, "base64"))
  // Reject non-base64 payloads: the decoded bytes must re-encode identically.
  if (Buffer.from(bytes).toString("base64") !== data.replace(/\s/g, "")) throw unavailable()
  if (bytes.length === 0) throw unavailable()
  checkPayload(bytes, mediaType)
  return bytes
}

export function createImageResolver(rootDir: string) {
  const root = path.resolve(rootDir)
  return async (resourceId: string, mediaType: string, signal: AbortSignal): Promise<ResolvedImage> => {
    if (!IMAGE_MIME_TYPES.has(mediaType)) {
      throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
    }
    const candidate = path.resolve(root, String(resourceId).replace(/\\/g, "/"))
    if (candidate !== root && !candidate.startsWith(root + path.sep)) {
      throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
    }
    // Walk every component under the root so a reparse point at any level is
    // rejected before the final read follows it.
    const unavailable = () => new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
    let current = root
    try {
      const relative = path.relative(root, candidate)
      for (const part of relative.split(path.sep)) {
        if (part === "" || part === "." || part === "..") throw unavailable()
        current = path.join(current, part)
        await assertNotReparse(current)
      }
    } catch (error) {
      if (error instanceof SidecarError) throw error
      throw unavailable()
    }
    if (signal.aborted) throw unavailable()
    let data: Buffer
    try {
      data = await readFile(current)
    } catch {
      throw unavailable()
    }
    checkPayload(data, mediaType)
    return { type: "image", data: Buffer.from(data).toString("base64"), mimeType: mediaType }
  }
}
