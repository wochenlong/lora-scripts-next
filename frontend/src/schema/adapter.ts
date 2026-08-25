import Schema from "schemastery"
import { i18n } from "../i18n"
import type { SchemaSource } from "../api/schemas"

export type FormValue = string | number | boolean | Array<string | number> | undefined
export type FormModel = Record<string, FormValue>

export function cloneFormValue(value: FormValue): FormValue {
  return Array.isArray(value) ? [...value] : value
}

export function cloneFormModel(model: FormModel): FormModel {
  return Object.fromEntries(Object.entries(model).map(([key, value]) => [key, cloneFormValue(value)]))
}

export interface FormCondition {
  key: string
  value: unknown
}

export interface FormField {
  key: string
  type: "string" | "number" | "boolean" | "array" | "const"
  description?: string
  role?: string
  extra?: Record<string, unknown>
  defaultValue?: FormValue
  constValue?: FormValue
  required?: boolean
  hidden?: boolean
  disabled?: boolean
  min?: number
  max?: number
  step?: number
  options?: FormValue[]
  conditions: FormCondition[]
}

export interface FormSection {
  id: string
  title: string
  fields: FormField[]
}

export interface AdaptedSchema {
  name: string
  hash: string
  schema: Schema
  sections: FormSection[]
}

type SchemaRecord = Schema & {
  type: string
  meta: Schema["meta"]
  dict?: Record<string, SchemaRecord>
  list?: SchemaRecord[]
  value?: FormValue
}

const SAMPLE_PROMPTS_DEFAULT = "(masterpiece, best quality:1.2), 1girl, solo, --n lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts,signature, watermark, username, blurry,  --w 512  --h 768  --l 7  --s 24  --d 1337"

function updateSchema<T extends Record<string, unknown>>(base: T, patch: Partial<T>, removed?: string[]) {
  const result = { ...base, ...patch }
  removed?.forEach((key) => delete result[key])
  return result
}

function execute(source: string, shared?: unknown) {
  const runtimeWindow = {
    __MIKAZUKI__: {
      SAMPLE_PROMPTS_DEFAULT,
      SAMPLE_PROMPTS_DESCRIPTION: i18n.global.t("schema.samplePromptsDescription"),
    },
  }
  const expression = source.trim().replace(/;\s*$/, "")
  const evaluate = new Function("Schema", "SHARED_SCHEMAS", "UpdateSchema", "window", `"use strict"; return (${expression});`)
  return evaluate(Schema, shared, updateSchema, runtimeWindow) as SchemaRecord | Record<string, unknown>
}

export function executeSchemaSources(sources: SchemaSource[], name: string): AdaptedSchema {
  const sharedSource = sources.find((item) => item.name === "shared")
  const target = sources.find((item) => item.name === name)
  if (!target) throw new Error(i18n.global.t("schema.notProvided", { name }))

  const shared = sharedSource ? execute(sharedSource.schema) : undefined
  const schema = execute(target.schema, shared) as SchemaRecord
  if (typeof schema !== "function" || !schema.type) throw new Error(i18n.global.t("schema.invalid", { name }))

  return {
    name,
    hash: target.hash,
    schema,
    sections: buildSections(schema),
  }
}

function description(meta: Schema["meta"] | undefined) {
  if (typeof meta?.description === "string") return meta.description
  return meta?.description?.["zh-CN"] || meta?.description?.[""]
}

function explicitDefault(schema: SchemaRecord) {
  if (!Object.prototype.hasOwnProperty.call(schema.meta ?? {}, "default")) return undefined
  const value = schema.meta.default as FormValue
  if (schema.type === "array" && Array.isArray(value) && value.length === 0) return undefined
  return value
}

function conditionsFrom(schema: SchemaRecord): FormCondition[] {
  if (schema.type === "object") {
    return Object.entries(schema.dict ?? {})
      .filter(([, field]) => field.type === "const" && !field.meta.hidden)
      .map(([key, field]) => ({ key, value: field.value }))
  }
  if (schema.type === "intersect") return (schema.list ?? []).flatMap(conditionsFrom)
  return []
}

function fieldFrom(key: string, schema: SchemaRecord, conditions: FormCondition[]): FormField | undefined {
  if (schema.type === "union" && schema.list?.every((item) => item.type === "const")) {
    return {
      key,
      type: "string",
      description: description(schema.meta),
      defaultValue: explicitDefault(schema),
      required: schema.meta.required,
      hidden: schema.meta.hidden,
      disabled: schema.meta.disabled,
      options: schema.list.map((item) => item.value),
      conditions,
    }
  }
  if (!["string", "number", "boolean", "array", "const"].includes(schema.type)) return undefined
  return {
    key,
    type: schema.type as FormField["type"],
    description: description(schema.meta),
    role: schema.meta.role,
    extra: schema.meta.extra,
    defaultValue: explicitDefault(schema),
    constValue: schema.value,
    required: schema.meta.required,
    hidden: schema.meta.hidden,
    disabled: schema.meta.disabled,
    min: schema.meta.min,
    max: schema.meta.max,
    step: schema.meta.step,
    conditions,
  }
}

function collectFields(schema: SchemaRecord, conditions: FormCondition[] = []): FormField[] {
  if (schema.type === "object") {
    return Object.entries(schema.dict ?? {}).flatMap(([key, child]) => {
      const field = fieldFrom(key, child, conditions)
      return field ? [field] : collectFields(child, conditions)
    })
  }
  if (schema.type === "intersect") return (schema.list ?? []).flatMap((child) => collectFields(child, conditions))
  if (schema.type === "union") {
    return (schema.list ?? []).flatMap((branch) => {
      const branchConditions = conditionsFrom(branch)
      const conditionKeys = new Set(branchConditions.map((condition) => condition.key))
      return collectFields(branch, [...conditions, ...branchConditions]).filter((field) => !conditionKeys.has(field.key))
    })
  }
  return []
}

function buildSections(schema: SchemaRecord) {
  const roots = schema.type === "intersect" ? schema.list ?? [] : [schema]
  const sections: FormSection[] = []
  let unnamed = 0
  const push = (title: string | undefined, fields: FormField[]) => {
    if (!fields.length) return
    const previous = sections.at(-1)
    if (!title && previous) {
      previous.fields.push(...fields)
      return
    }
    const resolved = title || i18n.global.t("schema.advancedSection")
    sections.push({ id: `${resolved}-${unnamed++}`, title: resolved, fields })
  }
  const walk = (node: SchemaRecord) => {
    const title = description(node.meta)
    if (!title && node.type === "intersect") {
      for (const child of node.list ?? []) walk(child)
      return
    }
    push(title, collectFields(node))
  }
  for (const root of roots) walk(root)
  return sections
}

export function isFieldActive(field: FormField, model: FormModel) {
  return field.conditions.every((condition) => model[condition.key] === condition.value)
}

export function createDefaultModel(schema: AdaptedSchema): FormModel {
  const model: FormModel = {}
  for (const field of schema.sections.flatMap((section) => section.fields)) {
    const value = field.defaultValue ?? field.constValue
    if (value !== undefined && model[field.key] === undefined) model[field.key] = cloneFormValue(value)
  }
  return model
}

// Readonly fields (disabled/hidden/const discriminators like model_train_type) must
// always match the active schema; carry-over/autosave from another module may
// otherwise leak a foreign value in (e.g. anima-lora into the krea2 page).
export function applyReadonlyDefaults(schema: AdaptedSchema, model: FormModel, defaults: FormModel) {
  const seen = new Set<string>()
  for (const field of schema.sections.flatMap((section) => section.fields)) {
    if (seen.has(field.key)) continue
    seen.add(field.key)
    if (!(field.disabled || field.hidden || field.type === "const")) continue
    const value = defaults[field.key]
    if (value !== undefined) model[field.key] = cloneFormValue(value)
  }
}

export function serializeModel(schema: AdaptedSchema, model: FormModel) {
  const output: FormModel = {}
  for (const field of schema.sections.flatMap((section) => section.fields)) {
    if (!isFieldActive(field, model)) continue
    const value = field.type === "const" ? field.constValue : model[field.key]
    if (value === undefined || value === "" || (Array.isArray(value) && !value.length)) continue
    output[field.key] = cloneFormValue(value)
  }
  return output
}

export function validateModel(schema: AdaptedSchema, model: FormModel) {
  const errors: Record<string, string> = {}
  for (const field of schema.sections.flatMap((section) => section.fields)) {
    if (!isFieldActive(field, model) || field.hidden) continue
    const value = model[field.key]
    if (field.required && (value === undefined || value === "" || (Array.isArray(value) && !value.length))) {
      errors[field.key] = i18n.global.t("schema.required")
    } else if (typeof value === "number" && field.min !== undefined && value < field.min) {
      errors[field.key] = i18n.global.t("schema.tooSmall", { min: field.min })
    } else if (typeof value === "number" && field.max !== undefined && value > field.max) {
      errors[field.key] = i18n.global.t("schema.tooLarge", { max: field.max })
    }
  }
  return errors
}
