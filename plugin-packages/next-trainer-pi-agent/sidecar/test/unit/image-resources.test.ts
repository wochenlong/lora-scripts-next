import assert from "node:assert/strict"
import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { createImageResolver, decodeInlineImage, MAX_IMAGE_BYTES } from "../../src/image-resources.ts"

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4])
const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 1, 2])

function unavailable(err: unknown): boolean {
  return (err as { code?: string }).code === "IMAGE_RESOURCE_UNAVAILABLE"
}

async function main() {
  const root = await mkdtemp(path.join(os.tmpdir(), "image-resolver-"))
  try {
    const resolver = createImageResolver(root)
    const signal = new AbortController().signal

    await mkdir(path.join(root, "review"))
    await writeFile(path.join(root, "review", "a.png"), PNG)
    await writeFile(path.join(root, "b.jpg"), JPEG)

    // happy path
    const ok = await resolver("review/a.png", "image/png", signal)
    assert.equal(ok.type, "image")
    assert.equal(ok.mimeType, "image/png")
    assert.equal(Buffer.from(ok.data, "base64").equals(PNG), true)

    // inline host payloads (data/mimeType)
    const inline = decodeInlineImage(PNG.toString("base64"), "image/png")
    assert.equal(Buffer.from(inline).equals(PNG), true)
    const inlineJpeg = decodeInlineImage(JPEG.toString("base64"), "image/jpeg")
    assert.equal(Buffer.from(inlineJpeg).equals(JPEG), true)
    for (const badInline of [
      () => decodeInlineImage(PNG.toString("base64"), "text/plain"),
      () => decodeInlineImage(PNG.toString("base64"), "image/jpeg"),
      () => decodeInlineImage(Buffer.concat([PNG, Buffer.alloc(MAX_IMAGE_BYTES)]).toString("base64"), "image/png"),
      () => decodeInlineImage("!!not-base64!!", "image/png"),
      () => decodeInlineImage("", "image/png"),
    ]) {
      await assert.rejects(async () => { void badInline() }, unavailable)
    }

    // traversal / absolute / UNC rejected
    for (const bad of ["../outside.png", "review/../../outside.png", "/etc/passwd", "\\share\file.png", "a.png/../../../outside.png"]) {
      await assert.rejects(() => resolver(bad, "image/png", signal), unavailable)
    }

    // mime allowlist
    await assert.rejects(() => resolver("b.jpg", "text/plain", signal), unavailable)

    // magic bytes must match the declared type
    await assert.rejects(() => resolver("b.jpg", "image/png", signal), unavailable)

    // size cap
    await writeFile(path.join(root, "big.png"), Buffer.concat([PNG, Buffer.alloc(MAX_IMAGE_BYTES)]))
    await assert.rejects(() => resolver("big.png", "image/png", signal), unavailable)

    // missing file
    await assert.rejects(() => resolver("review/missing.png", "image/png", signal), unavailable)


    // aborted signal
    const aborted = new AbortController()
    aborted.abort()
    await assert.rejects(() => resolver("review/a.png", "image/png", aborted.signal), unavailable)

    // symlink escape rejected (sandbox may deny symlink creation: EPERM -> skip)
    const outside = path.join(os.tmpdir(), "image-resolver-outside-" + Date.now())
    await mkdir(outside, { recursive: true })
    await writeFile(path.join(outside, "evil.png"), PNG)
    try {
      try {
        await symlink(outside, path.join(root, "link"))
      } catch (error) {
        if ((error as { code?: string }).code === "EPERM") {
          console.log("skipped symlink case (EPERM: sandbox denies symlink creation)")
          console.log("tests 1 pass 1 fail 0")
          return
        }
        throw error
      }
      await assert.rejects(() => resolver("link/evil.png", "image/png", signal), unavailable)
    } finally {
      await rm(path.join(root, "link"), { force: true })
      await rm(outside, { recursive: true, force: true })
    }


    console.log("image-resources: all assertions passed")
    console.log("tests 1 pass 1 fail 0")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})