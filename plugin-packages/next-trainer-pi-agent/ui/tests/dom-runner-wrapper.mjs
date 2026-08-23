// Headless DOM runner wrapper for spawn-restricted execution environments.
//
// Vitest's jsdom environment cannot be used here because its config loader
// spawns child processes.  This wrapper loads jsdom directly from
// node_modules, installs the DOM globals, and then imports the prebundled
// test (built with `bun build`, which inlines the vitest-compatible shim).
import { pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://127.0.0.1:28000/",
  pretendToBeVisual: true,
});

const globals = [
  "window",
  "document",
  "navigator",
  "localStorage",
  "sessionStorage",
  "Storage",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "HTMLIFrameElement",
  "HTMLAnchorElement",
  "HTMLButtonElement",
  "HTMLSelectElement",
  "HTMLImageElement",
  "Element",
  "Node",
  "Text",
  "Comment",
  "SVGElement",
  "CustomEvent",
  "Event",
  "MouseEvent",
  "KeyboardEvent",
  "InputEvent",
  "FocusEvent",
  "getComputedStyle",
  "requestAnimationFrame",
  "cancelAnimationFrame",
  "DOMParser",
  "MutationObserver",
  "Image",
  "File",
  "FileReader",
  "FormData",
  "matchMedia",
];
for (const key of globals) {
  try {
    if (globalThis[key] === undefined) {
      Object.defineProperty(globalThis, key, { value: dom.window[key], writable: true, configurable: true });
    }
  } catch {
    /* host global wins */
  }
}

const bundle = process.argv[2];
if (!bundle) {
  console.error("usage: bun dom-runner-wrapper.mjs <bundle.js>");
  process.exit(2);
}
await import(pathToFileURL(bundle).href);
