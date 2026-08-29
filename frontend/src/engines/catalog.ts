import type { TrainingEngine } from "../training/modules"

/** Shared runtime lifecycle for optional / planned engines. */
export type EngineRuntimeState =
  | "ready"
  | "not_installed"
  | "unknown"
  | "installing"
  | "auditing"
  | "broken"
  | "disabled"
  | "coming_soon"
  | "installed_unverified"

export type EngineKind = "builtin" | "optional" | "planned"

export interface EngineDefinition {
  id: TrainingEngine
  kind: EngineKind
  /** i18n key under settings.engines.catalog.<id> */
  nameKey: string
  summaryKey: string
  /** Shown for optional engines that download large runtimes. */
  sizeHintKey?: string
  requiresGpu?: boolean
  managesRuntime: boolean
  /** Short mark for logo tile (UI). */
  mark: string
  /** Capability tags shown on cards (i18n keys under settings.engines.tags.*). */
  tags: readonly string[]
  /** Display version (UI metadata; not a live feed). */
  version: string
  /** Display last-updated date (UI metadata). */
  updatedAt: string
  recommended?: boolean
}

/** Product cold-start / global default engine (Kohya). UI-only marker. */
export const PRODUCT_DEFAULT_ENGINE: TrainingEngine = "kohya"

export const ENGINE_CATALOG: readonly EngineDefinition[] = [
  {
    id: "kohya",
    kind: "builtin",
    nameKey: "settings.engines.catalog.kohya.name",
    summaryKey: "settings.engines.catalog.kohya.summary",
    managesRuntime: false,
    mark: "K",
    tags: ["lora", "sd15", "sdxl", "flux", "anima"],
    version: "builtin",
    updatedAt: "—",
  },
  {
    id: "anima-fast",
    kind: "optional",
    nameKey: "settings.engines.catalog.anima-fast.name",
    summaryKey: "settings.engines.catalog.anima-fast.summary",
    sizeHintKey: "settings.engines.catalog.anima-fast.sizeHint",
    requiresGpu: true,
    managesRuntime: true,
    mark: "AF",
    tags: ["lora", "anima", "nvidia"],
    version: "plugin",
    updatedAt: "2026-08",
    recommended: true,
  },
  {
    id: "musubi",
    kind: "optional",
    nameKey: "settings.engines.catalog.musubi.name",
    summaryKey: "settings.engines.catalog.musubi.summary",
    sizeHintKey: "settings.engines.catalog.musubi.sizeHint",
    requiresGpu: true,
    managesRuntime: true,
    mark: "M",
    tags: ["lora", "krea2", "nvidia"],
    version: "plugin",
    updatedAt: "2026-08",
  },
  {
    id: "ai-toolkit",
    kind: "optional",
    nameKey: "settings.engines.catalog.ai-toolkit.name",
    summaryKey: "settings.engines.catalog.ai-toolkit.summary",
    sizeHintKey: "settings.engines.catalog.ai-toolkit.sizeHint",
    requiresGpu: true,
    managesRuntime: true,
    mark: "AT",
    tags: ["lora", "klein", "nvidia"],
    version: "plugin",
    updatedAt: "2026-08",
  },
] as const

export function engineDefinition(id: TrainingEngine): EngineDefinition | undefined {
  return ENGINE_CATALOG.find((engine) => engine.id === id)
}
