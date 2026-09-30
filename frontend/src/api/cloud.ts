import { apiData } from "./client"

export interface CloudStatus {
  cloud_mode: boolean
  engine: string | null
}

export const cloudApi = {
  async status(): Promise<CloudStatus> {
    return apiData<CloudStatus>("/api/cloud/status")
  },
}
