import { computed, ref } from "vue"
import { cloudApi, type CloudStatus } from "../api/cloud"

const status = ref<CloudStatus>({ cloud_mode: false, engine: null })
let requested = false

export function useCloudMode() {
  async function refreshCloud() {
    try {
      status.value = await cloudApi.status()
    } catch {
      // 非云端或后端无此接口时保持关闭
    }
  }
  if (!requested) {
    requested = true
    void refreshCloud()
  }
  return {
    cloud: status,
    cloudMode: computed(() => status.value.cloud_mode),
    lockedEngine: computed(() => status.value.engine),
    refreshCloud,
  }
}
