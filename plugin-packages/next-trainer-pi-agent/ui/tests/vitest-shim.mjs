// Minimal vitest-compatible runner for spawn-restricted execution
// environments.  Implements exactly the API surface used by the DOM tests
// (describe/test/expect with .not, vi.fn, vi.spyOn, per-test cleanup) on top
// of the host runtime's DOM.  Loaded via the Bun onResolve redirect.
import assert from "node:assert/strict";
import { isDeepStrictEqual } from "node:util";

// DOM setup is installed by the runner wrapper (dom-runner-wrapper.mjs) via
// this synchronous hook when the host runtime does not expose DOM globals.
// (vitest normally provides the jsdom environment.)
const domSetup = globalThis.__DSH_DOM_SETUP__ ?? null;
if (typeof globalThis.document === "undefined" && typeof domSetup === "function") {
  domSetup();
}

const queue = [];
let currentPrefix = "";

export function describe(name, fn) {
  const prev = currentPrefix;
  currentPrefix = prev ? `${prev} > ${name}` : name;
  fn();
  currentPrefix = prev;
}

export const it = (name, fn) => {
  queue.push({ name: currentPrefix ? `${currentPrefix} > ${name}` : name, fn });
};
export const test = it;

function subsetMatch(expected, actual) {
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) return false;
    return expected.every((item, i) => subsetMatch(item, actual[i]));
  }
  if (expected !== null && typeof expected === "object") {
    if (actual === null || typeof actual !== "object") return false;
    return Object.entries(expected).every(([key, value]) => subsetMatch(value, actual[key]));
  }
  return isDeepStrictEqual(expected, actual);
}

const spies = [];

export const vi = {
  fn(impl) {
    const f = (...args) => {
      f.mock.calls.push(args);
      try {
        const value = impl ? impl(...args) : undefined;
        f.mock.results.push({ type: "return", value });
        return value;
      } catch (error) {
        f.mock.results.push({ type: "throw", value: error });
        throw error;
      }
    };
    f.mock = { calls: [], results: [] };
    f.mockClear = () => {
      f.mock.calls = [];
      f.mock.results = [];
    };
    return f;
  },
  spyOn(target, name) {
    const original = target[name];
    const f = vi.fn((...args) => original.apply(target, args));
    Object.defineProperty(target, name, { value: f, writable: true, configurable: true });
    spies.push({ target, name, original });
    return f;
  },
  clearAllMocks() {
    for (const spy of spies) spy.target[spy.name].mockClear?.();
  },
  restoreAllMocks() {
    while (spies.length) {
      const { target, name, original } = spies.pop();
      Object.defineProperty(target, name, { value: original, writable: true, configurable: true });
    }
  },
};

function matchers(actual, negated) {
  const check = (ok, message) => {
    const passed = negated ? !ok : ok;
    assert.ok(passed, negated ? `expected NOT (${message}), but it held` : message);
  };
  return {
    toBe: (expected) => check(isDeepStrictEqual(actual, expected), `toBe: ${JSON.stringify(actual)} -> ${JSON.stringify(expected)}`),
    toBeNull: () => check(actual === null, "toBeNull"),
    toBeInstanceOf: (ctor) => check(actual instanceof ctor, "toBeInstanceOf"),
    toBeGreaterThanOrEqual: (n) => check(actual >= n, `toBeGreaterThanOrEqual(${n})`),
    toBeLessThan: (n) => check(actual < n, `toBeLessThan(${n})`),
    toContain: (v) => check(typeof actual === "string" ? actual.includes(v) : Array.isArray(actual) && actual.includes(v), "toContain"),
    toEqual: (expected) => check(isDeepStrictEqual(actual, expected), "toEqual"),
    toHaveLength: (n) => check(actual?.length === n, `toHaveLength(${n}), got ${actual?.length}`),
    toMatchObject: (subset) => check(subsetMatch(subset, actual), "toMatchObject"),
    toHaveBeenCalled: () => check(Array.isArray(actual?.mock?.calls) && actual.mock.calls.length > 0, "toHaveBeenCalled"),
    toHaveBeenCalledWith: (...args) => check(Array.isArray(actual?.mock?.calls) && actual.mock.calls.some((call) => isDeepStrictEqual(call, args)), "toHaveBeenCalledWith"),
  };
}

function promiseMatchers(actual, negated) {
  const check = async (ok, message) => {
    const passed = negated ? !ok : ok;
    assert.ok(passed, negated ? `expected NOT (${message}), but it held` : message);
  };
  return {
    toBe: async (expected) => check(isDeepStrictEqual(await actual, expected), "resolves.toBe"),
    toEqual: async (expected) => check(isDeepStrictEqual(await actual, expected), "resolves.toEqual"),
    toBeNull: async () => check((await actual) === null, "resolves.toBeNull"),
    toMatchObject: async (subset) => check(subsetMatch(subset, await actual), "resolves.toMatchObject"),
  };
}

function rejectionMatchers(actual, negated) {
  const check = async (ok, message) => {
    const passed = negated ? !ok : ok;
    assert.ok(passed, negated ? `expected NOT (${message}), but it held` : message);
  };
  return {
    toBeInstanceOf: async (ctor) => check((await actual.catch((e) => e)) instanceof ctor, "rejects.toBeInstanceOf"),
    toEqual: async (expected) => check(isDeepStrictEqual(await actual.catch((e) => e), expected), "rejects.toEqual"),
    toMatchObject: async (subset) => check(subsetMatch(subset, await actual.catch((e) => e)), "rejects.toMatchObject"),
  };
}

export function expect(actual) {
  const api = matchers(actual, false);
  api.not = matchers(actual, true);
  api.resolves = promiseMatchers(actual, false);
  api.rejects = rejectionMatchers(actual, false);
  api.not.resolves = promiseMatchers(actual, true);
  api.not.rejects = rejectionMatchers(actual, true);
  return api;
}

async function runAll() {
  let passed = 0;
  let failed = 0;
  const failures = [];
  for (const item of queue) {
    try {
      await item.fn();
      passed += 1;
      console.log(`ok - ${item.name}`);
    } catch (error) {
      failed += 1;
      failures.push({ name: item.name, error });
      console.log(`FAIL - ${item.name}`);
    } finally {
      try {
        const { cleanup } = await import("@testing-library/react");
        cleanup();
      } catch {
        /* no DOM available */
      }
      try {
        globalThis.localStorage?.clear?.();
        globalThis.sessionStorage?.clear?.();
      } catch {
        /* ignore */
      }
      vi.restoreAllMocks();
    }
  }
  console.log(`# tests ${passed + failed}`);
  console.log(`# pass ${passed}`);
  console.log(`# fail ${failed}`);
  for (const failure of failures) {
    console.log(`--- ${failure.name}`);
    console.log(failure.error?.stack ?? String(failure.error));
  }
  if (failed > 0) process.exitCode = 1;
}

setImmediate(async () => {
  await runAll();
});
