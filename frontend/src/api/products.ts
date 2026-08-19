import { apiData } from "./client"

export type ProductStatus = "present" | "missing"

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
  deployed_to: Record<string, string>
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
}
