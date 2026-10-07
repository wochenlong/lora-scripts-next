import { afterEach, describe, expect, it, vi } from "vitest"
import { taggerApi, type CaptionJobReport, type CaptionJobStatus } from "../api/tagger"
import { useTaggerJob } from "./useTaggerJob"

vi.mock("../api/tagger", () => ({ taggerApi: { captionStatus: vi.fn(), captionStart: vi.fn(), captionCancel: vi.fn(), captionRetryFailed: vi.fn(), captionHistory: vi.fn(), captionReport: vi.fn() } }))
const status = (job_id: string): CaptionJobStatus => ({ job_id, phase: "done", mode: "natural", message: "done", current: 1, total: 1, filename: "", succeeded: 1, failed: 0, cancelled: 0, errors: [], updated_at: 1 })
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
afterEach(() => vi.resetAllMocks())

describe("caption task lifecycle", () => {
  it("coalesces overlapping polls and discards replies after leaving the page", async () => {
    const pending = deferred<CaptionJobStatus>()
    vi.mocked(taggerApi.captionStatus).mockReturnValueOnce(pending.promise)
    const job = useTaggerJob()
    job.activate()
    const first = job.refresh()
    const second = job.refresh()
    expect(first).toBe(second)
    expect(taggerApi.captionStatus).toHaveBeenCalledOnce()
    const signal = vi.mocked(taggerApi.captionStatus).mock.calls[0][0]!
    job.deactivate()
    expect(signal.aborted).toBe(true)
    pending.resolve(status("stale"))
    await first
    expect(job.status.value.job_id).toBeNull()
  })

  it("does not let an old poll overwrite a cancellation response", async () => {
    const pending = deferred<CaptionJobStatus>()
    vi.mocked(taggerApi.captionStatus).mockReturnValueOnce(pending.promise)
    vi.mocked(taggerApi.captionCancel).mockResolvedValue({ ...status("current"), phase: "cancelling" })
    const job = useTaggerJob()
    job.activate()
    const poll = job.refresh()
    await job.cancel()
    pending.resolve(status("old"))
    await poll
    expect(job.status.value.job_id).toBe("current")
    expect(job.status.value.phase).toBe("cancelling")
  })

  it("keeps the most recently selected report when earlier replies arrive late", async () => {
    const old = deferred<CaptionJobReport>()
    const recent = deferred<CaptionJobReport>()
    vi.mocked(taggerApi.captionReport).mockReturnValueOnce(old.promise).mockReturnValueOnce(recent.promise)
    const job = useTaggerJob()
    const first = job.loadReport("old")
    const second = job.loadReport("recent")
    recent.resolve({ job_id: "recent", phase: "done", snapshot: {}, report: { items: [] } })
    await second
    old.resolve({ job_id: "old", phase: "done", snapshot: {}, report: { items: [] } })
    await first
    expect(job.report.value?.job_id).toBe("recent")
    expect(job.reportBusy.value).toBe(false)
  })

  it("restores server recovery state and retries only through the retry endpoint", async () => {
    vi.mocked(taggerApi.captionStatus).mockResolvedValue({ ...status("recovered"), phase: "error", recovered: true, failed: 1 })
    vi.mocked(taggerApi.captionRetryFailed).mockResolvedValue({ ...status("retry"), phase: "pending", parent_job_id: "recovered" })
    const job = useTaggerJob()
    job.activate()
    await job.refresh()
    expect(job.status.value.recovered).toBe(true)
    await job.retry()
    expect(taggerApi.captionRetryFailed).toHaveBeenCalledOnce()
    expect(taggerApi.captionStart).not.toHaveBeenCalled()
    expect(job.status.value.parent_job_id).toBe("recovered")
  })
})
