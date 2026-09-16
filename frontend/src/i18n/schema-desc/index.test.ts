// @vitest-environment jsdom
import { readdirSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { DEFAULT_LOCALE, setLocale } from "../index"
import { schemaDescMessages } from "./index"
import { executeSchemaSources } from "../../schema/adapter"

const SCHEMA_DIR = resolve(__dirname, "../../../../mikazuki/schema")

export function extractSchemaDescriptions(dir = SCHEMA_DIR): string[] {
  const keys = new Set<string>()
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".ts"))) {
    const source = readFileSync(resolve(dir, file), "utf8")
    const pattern = /\.description\(\s*(["'])((?:\\.|(?!\1)[^])*?)\1\s*\)/g
    let match: RegExpExecArray | null
    while ((match = pattern.exec(source))) {
      keys.add(eval(`${match[1]}${match[2]}${match[1]}`) as string)
    }
  }
  return [...keys].sort()
}

describe("schema description translations", () => {
  afterEach(() => {
    setLocale(DEFAULT_LOCALE)
  })

  it("keeps every registered locale in parity with the schema sources", () => {
    const expected = extractSchemaDescriptions()
    expect(expected.length).toBeGreaterThan(0)
    for (const [locale, messages] of Object.entries(schemaDescMessages)) {
      expect(Object.keys(messages).sort(), `schemaDesc parity for ${locale}`).toEqual(expected)
    }
  })

  it("translates field descriptions and section titles for the active locale", () => {
    schemaDescMessages["en-US"] = {
      "训练种类": "Training Type",
      "数据集设置": "Dataset Settings",
    }
    const sources = [
      { name: "shared", hash: "shared", schema: "(() => ({}))()" },
      {
        name: "sample",
        hash: "sample",
        schema: `Schema.intersect([
          Schema.object({ model_train_type: Schema.string().description('训练种类') }).description('数据集设置'),
        ])`,
      },
    ]
    setLocale("en-US")
    const adapted = executeSchemaSources(sources, "sample")
    expect(adapted.sections[0].title).toBe("Dataset Settings")
    expect(adapted.sections[0].fields[0].description).toBe("Training Type")
    delete schemaDescMessages["en-US"]
  })

  it("falls back to the original text when no translation exists", () => {
    schemaDescMessages["en-US"] = {}
    const sources = [
      {
        name: "sample",
        hash: "sample",
        schema: "Schema.object({ model_train_type: Schema.string().description('训练种类') })",
      },
    ]
    setLocale("en-US")
    const adapted = executeSchemaSources(sources, "sample")
    expect(adapted.sections[0].fields[0].description).toBe("训练种类")
    delete schemaDescMessages["en-US"]
  })
})
