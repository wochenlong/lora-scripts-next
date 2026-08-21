# Next Trainer Pi Agent plugin

Optional marketplace plugin source. It is not imported by the Next Trainer core and is not part of the default core distribution.

## Runtime baseline

- Build/test Node: exactly 22.19.x (`.nvmrc` and `engine-strict`).
- Pi SDK: exactly 0.84.2.
- Distributed sidecar: Bun 1.4.0 standalone Windows x64 baseline executable.
- Network: fixed loopback listener; the browser iframe never connects to the sidecar directly.

## Development

```powershell
npm ci --ignore-scripts
npm run check
```

The initial skeleton exposes authenticated health, provider-profile and session/event seams. The production Pi adapter is intentionally isolated behind `PiRuntimeAdapter`; tests use an in-memory adapter and do not imply that the real Provider path is complete.

No Provider key may be stored in browser persistence, logged, returned by a status route, committed, or included in evidence.
