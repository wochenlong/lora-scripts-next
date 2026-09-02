/**
 * Host-UI refresh scheduling for plugin lifecycle changes.
 *
 * A successful marketplace action (install / uninstall / enable / disable /
 * rollback / restart) changes which plugin UI the host shell must mount or
 * unmount. The floating panel only remounts when its
 * pluginId+mode+entryUrl key changes, so a fresh install can leave it stuck
 * on a stale "not ready" view and an uninstalled plugin's panel can linger.
 * Scheduling a real page reload after a short delay (so the success toast is
 * visible first) is the deterministic fix the user asked for: the whole SPA —
 * extensions store, floating panel, plugin pages — remounts from live state.
 */

export const HOST_REFRESH_DELAY_MS = 1200

export function scheduleHostRefresh(reload: () => void = () => window.location.reload()): number {
  return window.setTimeout(reload, HOST_REFRESH_DELAY_MS)
}
