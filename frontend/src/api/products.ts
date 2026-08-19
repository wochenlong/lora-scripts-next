import { apiData } from "./client"

export type ProductStatus = "present" | "missing"

export interface DeployEntry {
  path: string
  desired: "deployed" | "removed"
  method?: string
  size?: number
  mtime?: number
  deployed_at?: number
}

export interface Product {
  id: string
  name: string
  path: string
  size: number | null
  mtime: number | null
  group_key: string
  epoch: number | null
  step: number | null
  dim: number | null
  alpha: number | null
  base_model_version: string | null
  sd_model_name: string | null
  network_module: string | null
  family: string
  is_lycoris: boolean
  run_task_id: string | null
  train_type: string | null
  derived_from: string | null
  deployed_to: Record<string, DeployEntry>
  deploy_status?: Record<string, string>
  status: ProductStatus
}

export interface ProductGroup {
  key: string
  name: string
  output_dir: string
  family: string
  train_type: string | null
  run_task_id: string | null
  products: Product[]
}

export interface ProductListData {
  groups: ProductGroup[]
  families: string[]
  scanned_dirs: string[]
  deploy_targets: Record<string, string>
}

export interface ProductRun {
  task_id: string
  registered_at?: number
  train_type?: string
  config_path?: string | null
  output_dir?: string | null
  output_name?: string | null
  logging_dir?: string | null
  config_exists?: boolean
}

export interface ProductDetail extends Product {
  metadata?: Record<string, string>
  run?: ProductRun | null
}

export interface ProductScanData {
  scanned_dirs: string[]
  added_dirs: string[]
  total: number
}

export const productsApi = {
  list: (family?: string) =>
    apiData<ProductListData>(`/api/products${family ? `?family=${encodeURIComponent(family)}` : ""}`),
  scan: (dirs: string[] = []) =>
    apiData<ProductScanData>("/api/products/scan", { method: "POST", body: JSON.stringify({ dirs }) }),
  detail: (id: string) =>
    apiData<{ product: ProductDetail }>(`/api/products/${encodeURIComponent(id)}`),
  resolvePath: (path: string) =>
    apiData<{ path: string; resolved: string | null }>(`/api/products/resolve-path?path=${encodeURIComponent(path)}`),
  downloadUrl: (id: string) => `/api/products/${encodeURIComponent(id)}/download`,
  addDeployTarget: (name: string, path: string) =>
    apiData<{ targets: Record<string, string> }>("/api/products/deploy/targets", {
      method: "POST",
      body: JSON.stringify({ name, path }),
    }),
  removeDeployTarget: (name: string) =>
    apiData<{ targets: Record<string, string> }>(`/api/products/deploy/targets/${encodeURIComponent(name)}`, { method: "DELETE" }),
  deploy: (id: string, target: string, method: "copy" | "link" = "copy") =>
    apiData<{ status: string; path: string; method?: string }>(`/api/products/${encodeURIComponent(id)}/deploy`, {
      method: "POST",
      body: JSON.stringify({ target, method }),
    }),
  undeploy: (id: string, target: string) =>
    apiData<{ status: string }>(`/api/products/${encodeURIComponent(id)}/undeploy`, {
      method: "POST",
      body: JSON.stringify({ target }),
    }),
  reconcile: () =>
    apiData<{ results: { id: string; target: string; status: string; message?: string }[] }>(
      "/api/products/deploy/reconcile", { method: "POST", body: "{}" },
    ),
  remove: (id: string) =>
    apiData<{ deleted: string }>(`/api/products/${encodeURIComponent(id)}`, { method: "DELETE" }),
  updateMetadata: (id: string, metadata: Record<string, string>) =>
    apiData<{ backup: string; keys: number }>(`/api/products/${encodeURIComponent(id)}/metadata`, {
      method: "PUT",
      body: JSON.stringify({ metadata }),
    }),
  resize: (id: string, body: {
    output_path: string
    new_rank?: number | null
    new_conv_rank?: number | null
    dynamic_method?: string | null
    dynamic_param?: number | null
    save_precision?: string | null
  }) =>
    apiData<{ task_id: string; queued: boolean }>(`/api/products/${encodeURIComponent(id)}/actions/resize`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  merge: (body: { inputs: string[]; ratios: number[]; output_path: string; concat?: boolean; shuffle?: boolean }) =>
    apiData<{ task_id: string; queued: boolean }>("/api/products/actions/merge", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  extract: (id: string, body: { model_org: string; output_path: string; dim: number; conv_dim?: number | null; sdxl?: boolean; v2?: boolean }) =>
    apiData<{ task_id: string; queued: boolean }>(`/api/products/${encodeURIComponent(id)}/actions/extract`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
}
