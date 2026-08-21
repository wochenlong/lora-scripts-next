export interface ParentMonitor {
  stop(): void
}

export function startParentMonitor(
  parentAlive: () => boolean,
  onParentExit: () => Promise<void> | void,
  intervalMs = 1_000,
): ParentMonitor {
  let stopped = false
  let handlingExit = false
  const timer = setInterval(() => {
    if (stopped || handlingExit || parentAlive()) return
    handlingExit = true
    clearInterval(timer)
    void Promise.resolve(onParentExit()).finally(() => {
      stopped = true
    })
  }, intervalMs)
  timer.unref?.()
  return {
    stop(): void {
      if (stopped) return
      stopped = true
      clearInterval(timer)
    },
  }
}
