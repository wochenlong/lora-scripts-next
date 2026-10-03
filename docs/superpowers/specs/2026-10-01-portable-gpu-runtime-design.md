# Standalone GPU portable runtime

Status: design draft; implementation and acceptance pending.
Target: dev. Separate from the updater channel repair following PR #362.

## Evidence and limits

The historical 3.1.0 Fast artifact contains a Fast venv, but its pyvenv.cfg and
sys.base_prefix refer to the build machine's external Python.
Its main embedded interpreter cannot import torch or start the GUI when user
site packages are disabled. A Fast CUDA tensor operation succeeds on the build
machine, but that does not prove portability.

The base builder intentionally clears temporary site-packages after tagger
prefetch, and Copy-AnimaFastRuntime copies the venv without packaging its base
interpreter. Missing host dependencies in this artifact are therefore not
evidence that every existing Kohya/AIO builder is broken.

An initial probe omitted -s and imported user-site modules; its apparent host
GPU success is invalid acceptance evidence. Only isolated probes count.

## Decision

Keep lite intentionally minimal. Complete packages must carry their declared
host and engine dependencies, including each required base interpreter.
Use explicit package-flavor validation rather than relying on installed
maintenance-machine libraries or first-launch downloads.

For Fast, bundle its compatible base CPython alongside its environment and
repair location-dependent environment metadata before invoking it. Verify
actual interpreter/module paths afterward. Do not treat a pyvenv.cfg edit alone
as sufficient.

Reusing global Python or copying arbitrary developer site-packages is rejected.
Downloading missing dependencies on first launch is an installer fallback, not
offline-full-package readiness. An unconditional large offline wheelhouse is
not required; if environment reconstruction is necessary, its inputs must be
bundled and validated without a network dependency.

## Implementation boundaries

- Inspect current host, Kohya and Fast dependency entrypoints and reuse their
  declared requirements. Do not invent a second conflicting dependency list.
- Install using explicit package-local interpreters, no user installs or
  global interpreter mutation.
- Isolate build-time prefetch dependencies from final runtime dependencies,
  or install final dependencies after temporary cleanup.
- Disable user-site inheritance consistently in launchers, validation and
  dependency subprocesses. Never silently use system Python as a fallback.
- The complete Fast product includes GUI requirements and the isolated Fast
  runtime. Kohya and host torch are NOT required or installed by this profile.
  Preserve the existing lite/AIO flows separately.
- Bundle only the required base Python, not the entire developer runtime tree.
- Relocation repair must run before Fast audit/training, not just GUI startup.
- Validate sys.executable, sys.prefix, sys.base_prefix, imported dependency
  paths and entrypoint behavior after moving the package. Required runtime
  paths must resolve inside the moved package.
- Reject incomplete full packages before publishing. Keep lite behavior and
  intentional first-install semantics separate.
- Never include personal models, datasets, credentials or local documentation.

## Acceptance

- Fresh full GPU build with host and Fast dependencies installed in-package.
- Isolated imports and dependency consistency checks for declared components.
- Move/extract to a different directory; block access to build-machine Python
  in a disposable test environment, without renaming the user's live runtime.
- Disable network and user site; use no auto-install fallback.
- GUI root responds on a free loopback port; engine detection reports usable.
- Fast CUDA operation and short training succeed with supplied external test
  model/data; no user models are baked into the package.
- Test supported paths, including spaces, and repeat relocation.
- Validate shipped console entrypoints or use explicit interpreter -m calls.
- Final combined acceptance uses the updater repair: normal upgrade, repeated
  upgrade, restart, short training and unchanged user-data hashes.
- Record package size, SHA256, source commit, flavor and actual runtime paths.

## Scope and readiness

Use only independent build/extraction directories. No edits to the main working
tree, shared Python environments or existing services. Coordinate GPU testing
with current utilization; do not stop another process to make room.

This draft is not merge-ready. No new full/AIO build or standalone acceptance
has passed. Code tests can run independently of the updater PR, but combined
release acceptance requires both repairs.
