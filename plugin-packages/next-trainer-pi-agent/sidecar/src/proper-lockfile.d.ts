declare module "proper-lockfile" {
  interface LockOptions {
    realpath?: boolean
    stale?: number
    retries?: number | {
      retries?: number
      factor?: number
      minTimeout?: number
      maxTimeout?: number
    }
  }

  type Release = () => Promise<void>

  const lockfile: {
    lock(path: string, options?: LockOptions): Promise<Release>
  }

  export default lockfile
}
