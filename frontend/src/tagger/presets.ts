/** Product-recommended tagger profiles — task first, model name second. */

export type TaggerTask = "character" | "style" | "general"

export const TAGGER_TASKS: readonly TaggerTask[] = ["character", "style", "general"]

export interface TaggerPreset {
  model: string
  threshold: number
  characterThreshold: number
}

/**
 * Stable defaults for common LoRA data prep paths.
 * Character: keep more character tags. Style: raise character threshold to
 * suppress identity tags. General: balanced WD14 default.
 */
export const TAGGER_PRESETS: Readonly<Record<TaggerTask, TaggerPreset>> = {
  character: {
    model: "wd-swinv2-v3",
    threshold: 0.35,
    characterThreshold: 0.55,
  },
  style: {
    model: "wd-convnext-v3",
    threshold: 0.35,
    characterThreshold: 0.85,
  },
  general: {
    model: "wd14-convnextv2-v2",
    threshold: 0.35,
    characterThreshold: 0.6,
  },
}

export function presetForTask(task: TaggerTask): TaggerPreset {
  return TAGGER_PRESETS[task]
}

export function taskForModel(model: string): TaggerTask | undefined {
  const match = (Object.entries(TAGGER_PRESETS) as [TaggerTask, TaggerPreset][])
    .find(([, preset]) => preset.model === model)
  return match?.[0]
}
