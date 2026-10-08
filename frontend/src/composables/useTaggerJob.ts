import { computed, ref } from "vue"
import { taggerApi, type CaptionJobReport, type ModelTaggingRequest, type CaptionJobStatus } from "../api/tagger"

export function useTaggerJob() {
  const status = ref<CaptionJobStatus>({ job_id: null, phase: "idle", mode: null, message: "", current: 0, total: 0,
    filename: "", succeeded: 0, failed: 0, cancelled: 0, errors: [], updated_at: 0 })
  const error = ref("")
  const submitting = ref(false)
  const jobs = ref<CaptionJobStatus[]>([])
  const report = ref<CaptionJobReport | null>(null)
  const reportBusy = ref(false)
  const historyBusy = ref(false)
  const busy = computed(() => ["pending", "captioning", "cancelling"].includes(status.value.phase))
  let generation = 0
  let active = false
  let polling: Promise<void> | null = null
  let controller: AbortController | null = null
  let reportGeneration = 0

  function invalidate() {
    generation += 1
    controller?.abort()
    controller = null
  }

  function activate() { active = true }
  function deactivate() { active = false; invalidate(); reportGeneration += 1; reportBusy.value = false }

  function refresh(): Promise<void> {
    if (!active) return Promise.resolve()
    if (polling) return polling
    const revision = generation
    const request = new AbortController()
    controller = request
    const pending = (async () => {
      try {
        const next = await taggerApi.captionStatus(request.signal)
        if (active && revision === generation) {
          status.value = next
          error.value = ""
        }
      } catch (caught) {
        if (active && revision === generation && !request.signal.aborted) error.value = caught instanceof Error ? caught.message : String(caught)
      }
    })().finally(() => {
      if (polling === pending) polling = null
      if (controller === request) controller = null
    })
    polling = pending
    return pending
  }

  async function mutate(operation: () => Promise<CaptionJobStatus>) {
    if (submitting.value) return
    invalidate()
    const revision = generation
    submitting.value = true
    error.value = ""
    try {
      const next = await operation()
      if (revision === generation) status.value = next
    } catch (caught) {
      if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
      throw caught
    } finally {
      submitting.value = false
    }
  }

  const start = (request: ModelTaggingRequest) => mutate(() => taggerApi.captionStart(request))
  const cancel = () => mutate(() => taggerApi.captionCancel())
  const retry = () => mutate(() => taggerApi.captionRetryFailed())

  async function loadHistory() {
    if (historyBusy.value) return
    historyBusy.value = true
    const revision = generation
    try {
      const history = await taggerApi.captionHistory()
      if (revision === generation) jobs.value = history.jobs
    } catch (caught) {
      if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
    } finally { historyBusy.value = false }
  }

  async function loadReport(jobId: string) {
    const revision = ++reportGeneration
    reportBusy.value = true
    try {
      const next = await taggerApi.captionReport(jobId)
      if (revision === reportGeneration) report.value = next
    } catch (caught) {
      if (revision === reportGeneration) error.value = caught instanceof Error ? caught.message : String(caught)
    } finally {
      if (revision === reportGeneration) reportBusy.value = false
    }
  }

  return { status, error, submitting, busy, jobs, report, reportBusy, historyBusy,
    activate, deactivate, refresh, start, cancel, retry, loadHistory, loadReport }
}
