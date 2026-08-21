export class SidecarError extends Error {
  readonly status: number
  readonly code: string
  readonly retryable: boolean

  constructor(status: number, code: string, message: string, retryable = false) {
    super(message)
    this.name = "SidecarError"
    this.status = status
    this.code = code
    this.retryable = retryable
  }
}

export function toPublicError(error: unknown): SidecarError {
  if (error instanceof SidecarError) return error
  return new SidecarError(500, "INTERNAL_ERROR", "The sidecar could not complete the request.", false)
}
