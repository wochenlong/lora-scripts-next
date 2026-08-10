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
}

export const ENGINE_CATALOG: readonly EngineDefinition[] = [
  {
    id: "kohya",
    kind: "builtin",
    nameKey: "settings.engines.catalog.kohya.name",
    summaryKey: "settings.engines.catalog.kohya.summary",
    managesRuntime: false,
  },
  {
    id: "anima-fast",
    kind: "optional",
    nameKey: "settings.engines.catalog.anima-fast.name",
    summaryKey: "settings.engines.catalog.anima-fast.summary",
    sizeHintKey: "settings.engines.catalog.anima-fast.sizeHint",
    requiresGpu: true,
    managesRuntime: true,
  },
  {
    id: "musubi",
    kind: "optional",
    nameKey: "settings.engines.catalog.musubi.name",
    summaryKey: "settings.engines.catalog.musubi.summary",
    sizeHintKey: "settings.engines.catalog.musubi.sizeHint",
    requiresGpu: true,
    managesRuntime: true,
  },
] as const

export function engineDefinition(id: TrainingEngine): EngineDefinition | undefined {
  return ENGINE_CATALOG.find((engine) => engine.id === id)
}
