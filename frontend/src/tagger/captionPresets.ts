import { userPresetsApi, type UserPreset } from "../api/userPresets"

export const TAGGER_CAPTION_TRAIN_TYPE = "tagger-caption"
export const LEGACY_CAPTION_TEMPLATES_KEY = "nt.tagger.captionTemplates"
const LEGACY_MARKER_PREFIX = "legacy-tagger-caption:"

export interface CaptionPreset {
  id: string
  name: string
  prompt: string
  language: string
}

export interface CaptionPresetInput {
  name: string
  prompt: string
  language: string
}

interface CaptionPresetClient {
  list(trainType?: string): Promise<UserPreset[]>
  create(payload: Pick<UserPreset, "name" | "config"> & Partial<Pick<UserPreset, "train_type" | "description">>): Promise<UserPreset>
  update(id: string, payload: Partial<Pick<UserPreset, "name" | "config" | "description">>): Promise<UserPreset>
  remove(id: string): Promise<unknown>
}

function mapCaptionPreset(record: UserPreset): CaptionPreset | null {
  const prompt = record.config.prompt
  const language = record.config.language
  if (typeof record.id !== "string" || typeof record.name !== "string"
    || typeof prompt !== "string" || typeof language !== "string") return null
  return { id: record.id, name: record.name, prompt, language }
}

function requireCaptionPreset(record: UserPreset): CaptionPreset {
  const mapped = mapCaptionPreset(record)
  if (!mapped) throw new Error("Invalid tagger caption preset")
  return mapped
}

function presetPayload(input: CaptionPresetInput) {
  return {
    name: input.name,
    config: { prompt: input.prompt, language: input.language },
  }
}

function readLegacyTemplates(storage: Storage): Array<[string, string]> | null {
  const raw = storage.getItem(LEGACY_CAPTION_TEMPLATES_KEY)
  if (raw === null) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
    return Object.entries(parsed).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string" && Boolean(entry[1].trim()),
    )
  } catch {
    return null
  }
}

export function createCaptionPresetService(client: CaptionPresetClient = userPresetsApi) {
  async function listRecords() {
    return client.list(TAGGER_CAPTION_TRAIN_TYPE)
  }

  async function migrateLegacy(existing: UserPreset[], storage: Storage = localStorage): Promise<CaptionPreset[]> {
    const legacy = readLegacyTemplates(storage)
    if (legacy === null) return []
    if (!legacy.length) {
      if (storage.getItem(LEGACY_CAPTION_TEMPLATES_KEY) !== null) storage.removeItem(LEGACY_CAPTION_TEMPLATES_KEY)
      return []
    }

    const migrated: CaptionPreset[] = []
    for (const [name, prompt] of legacy) {
      const marker = `${LEGACY_MARKER_PREFIX}${name}`
      const found = existing.find(record => record.description === marker)
      if (found) {
        const mapped = mapCaptionPreset(found)
        if (mapped) migrated.push(mapped)
        continue
      }
      const created = await client.create({
        name,
        train_type: TAGGER_CAPTION_TRAIN_TYPE,
        description: marker,
        config: { prompt, language: "en" },
      })
      migrated.push(requireCaptionPreset(created))
    }
    storage.removeItem(LEGACY_CAPTION_TEMPLATES_KEY)
    return migrated
  }

  return {
    async list(): Promise<CaptionPreset[]> {
      return (await listRecords()).flatMap(record => {
        const mapped = mapCaptionPreset(record)
        return mapped ? [mapped] : []
      })
    },
    async load(storage: Storage = localStorage): Promise<CaptionPreset[]> {
      const records = await listRecords()
      const existing = records.flatMap(record => {
        const mapped = mapCaptionPreset(record)
        return mapped ? [mapped] : []
      })
      const migrated = await migrateLegacy(records, storage)
      const existingIds = new Set(existing.map(record => record.id))
      return [...existing, ...migrated.filter(record => !existingIds.has(record.id))]
    },
    async create(input: CaptionPresetInput): Promise<CaptionPreset> {
      return requireCaptionPreset(await client.create({
        ...presetPayload(input),
        train_type: TAGGER_CAPTION_TRAIN_TYPE,
      }))
    },
    async update(id: string, input: CaptionPresetInput): Promise<CaptionPreset> {
      return requireCaptionPreset(await client.update(id, presetPayload(input)))
    },
    async remove(id: string): Promise<void> {
      await client.remove(id)
    },
    migrateLegacy,
  }
}
