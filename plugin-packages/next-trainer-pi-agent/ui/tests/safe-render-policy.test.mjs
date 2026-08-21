import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyImageSource,
  classifyLinkTarget,
  SAFE_MARKDOWN_STRIP_TAGS,
} from "../src/rendering/safe-render-policy.ts";

test("external and artifact references are classified for host mediation", () => {
  assert.deepEqual(classifyLinkTarget("https://example.com/docs"), {
    kind: "external",
    url: "https://example.com/docs",
  });
  assert.deepEqual(classifyLinkTarget("artifact:training-config-1"), {
    kind: "artifact",
    artifactId: "training-config-1",
  });
});

test("active, local and relative references are blocked", () => {
  for (const value of [
    "javascript:alert(1)",
    "data:text/html;base64,SGVsbG8=",
    "file:///private.txt",
    "C:\\private.txt",
    "../private.txt",
    "artifact:bad id",
  ]) {
    assert.deepEqual(classifyLinkTarget(value), { kind: "blocked" });
  }
});

test("only non-vector inline images are accepted", () => {
  assert.equal(classifyImageSource("data:image/png;base64,iVBORw0KGgo=").kind, "inline");
  assert.equal(classifyImageSource("blob:null/123").kind, "inline");
  assert.equal(classifyImageSource("data:image/svg+xml;base64,PHN2Zz4=").kind, "blocked");
  assert.equal(classifyImageSource("https://example.com/image.png").kind, "blocked");
});

test("the sanitizer strip list covers executable and navigational elements", () => {
  for (const tag of ["script", "form", "iframe", "object", "style", "base", "embed"]) {
    assert.equal(SAFE_MARKDOWN_STRIP_TAGS.includes(tag), true);
  }
});
