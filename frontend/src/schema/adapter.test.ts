import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { applyReadonlyDefaults, createDefaultModel, executeSchemaSources, serializeModel } from "./adapter"

const sources = [
  {
    name: "shared",
    hash: "shared",
    schema: "(() => ({ COMMON: Schema.object({ output_name: Schema.string().default('model') }).description('保存设置') }))()",
  },
  {
    name: "training",
    hash: "training",
    schema: `Schema.intersect([
      Schema.object({
        enabled: Schema.boolean().default(false),
        mode: Schema.union(['a', 'b']).default('a'),
        hidden_value: Schema.const('fixed').default('fixed').hidden(),
      }).description('基础设置'),
      SHARED_SCHEMAS.COMMON,
      Schema.union([
        Schema.object({ enabled: Schema.const(true).required(), detail: Schema.number().min(1).default(2) }),
        Schema.object({}),
      ]),
    ])`,
  },
]

describe("dynamic schema adapter", () => {
  it("executes shared schemas and creates defaults", () => {
    const schema = executeSchemaSources(sources, "training")
    expect(createDefaultModel(schema)).toMatchObject({ enabled: false, mode: "a", hidden_value: "fixed", output_name: "model", detail: 2 })
  })

  it("serializes only fields from the active conditional branch", () => {
    const schema = executeSchemaSources(sources, "training")
    const model = createDefaultModel(schema)
    expect(serializeModel(schema, model)).not.toHaveProperty("detail")
    model.enabled = true
    expect(serializeModel(schema, model)).toMatchObject({ enabled: true, detail: 2 })
  })

  it("does not replace a controlling field with its conditional const", () => {
    const schema = executeSchemaSources(sources, "training")
    const enabledFields = schema.sections.flatMap((section) => section.fields).filter((field) => field.key === "enabled")
    expect(enabledFields).toHaveLength(1)
    expect(enabledFields[0].type).toBe("boolean")
  })

  it("treats non-required const fields as union discriminators", () => {
    const conditionalSources = [{
      name: "conditional",
      hash: "conditional",
      schema: `Schema.intersect([
        Schema.object({ mode: Schema.union(['sd-lora', 'sdxl-lora']).default('sdxl-lora') }),
        Schema.union([
          Schema.object({ mode: Schema.const('sd-lora'), v2: Schema.boolean().default(false) }),
          Schema.object({}),
        ]),
      ])`,
    }]
    const schema = executeSchemaSources(conditionalSources, "conditional")
    const modeFields = schema.sections.flatMap((section) => section.fields).filter((field) => field.key === "mode")
    expect(modeFields).toHaveLength(1)
    expect(modeFields[0].options).toEqual(["sd-lora", "sdxl-lora"])
  })

  it("serializes hidden const fields instead of treating them as discriminators", () => {
    const conditionalSources = [{
      name: "conditional",
      hash: "conditional",
      schema: `Schema.intersect([
        Schema.object({ mode: Schema.union(['a', 'b']).default('a') }),
        Schema.union([
          Schema.object({
            mode: Schema.const('a'),
            implementation: Schema.const('module.a').default('module.a').hidden(),
          }),
          Schema.object({
            mode: Schema.const('b'),
            implementation: Schema.const('module.b').default('module.b').hidden(),
          }),
        ]),
      ])`,
    }]
    const schema = executeSchemaSources(conditionalSources, "conditional")
    const model = createDefaultModel(schema)

    expect(serializeModel(schema, model)).toMatchObject({ mode: "a", implementation: "module.a" })
    model.mode = "b"
    expect(serializeModel(schema, model)).toMatchObject({ mode: "b", implementation: "module.b" })
  })

  it("expands untitled nested intersects into named sections", () => {
    const nestedSources = [{
      name: "nested",
      hash: "nested",
      schema: `Schema.intersect([
        Schema.object({ orphan: Schema.string() }),
        Schema.intersect([
          Schema.object({ learning_rate: Schema.string().default('1e-4') }).description('学习率与优化器设置'),
          Schema.union([
            Schema.object({ lr_warmup: Schema.number().default(0) }),
            Schema.object({}),
          ]),
        ]),
      ])`,
    }]
    const schema = executeSchemaSources(nestedSources, "nested")
    expect(schema.sections.map((section) => section.title)).toEqual(["高级设置", "学习率与优化器设置"])
    const lr = schema.sections[1]
    expect(lr.fields.map((field) => field.key)).toEqual(["learning_rate", "lr_warmup"])
  })

  it("names real backend schema sections instead of one giant advanced block", () => {
    const schemaDir = resolve(process.cwd(), "../mikazuki/schema")
    const realSources = readdirSync(schemaDir).filter((name) => name.endsWith(".ts")).map((file) => ({
      name: file.slice(0, -3),
      hash: file,
      schema: readFileSync(resolve(schemaDir, file), "utf8"),
    }))
    const master = executeSchemaSources(realSources, "lora-master")
    const titles = master.sections.map((section) => section.title)
    for (const expected of ["保存设置", "学习率与优化器设置", "网络设置", "训练预览图设置", "日志设置"]) {
      expect(titles).toContain(expected)
    }
    const lr = master.sections.find((section) => section.title === "学习率与优化器设置")!
    expect(lr.fields.map((field) => field.key)).toContain("optimizer_type")
    expect(lr.fields.map((field) => field.key)).toContain("lr_scheduler_num_cycles")
    expect(lr.fields.map((field) => field.key)).toContain("prodigy_d0")
    const log = master.sections.find((section) => section.title === "日志设置")!
    expect(log.fields.map((field) => field.key)).toContain("wandb_api_key")
    const preview = master.sections.find((section) => section.title === "训练预览图设置")!
    expect(preview.fields.map((field) => field.key)).toContain("sample_sampler")
  })

  it("restores readonly fields polluted by carry-over or autosave", () => {
    const lockedSources = [{
      name: "locked",
      hash: "locked",
      schema: `Schema.object({
        model_train_type: Schema.string().default('krea2-lora').disabled(),
        mode: Schema.const('musubi').default('musubi').hidden(),
        learning_rate: Schema.string().default('1e-4'),
      })`,
    }]
    const schema = executeSchemaSources(lockedSources, "locked")
    const defaults = createDefaultModel(schema)
    const model = { ...defaults, model_train_type: "anima-lora", mode: "foreign", learning_rate: "2e-4" }
    applyReadonlyDefaults(schema, model, defaults)
    expect(model).toMatchObject({ model_train_type: "krea2-lora", mode: "musubi", learning_rate: "2e-4" })
  })

  it("does not invent array defaults when the schema omits them", () => {
    const arraySources = [{
      name: "arrays",
      hash: "arrays",
      schema: "Schema.object({ tags: Schema.array(String), names: Schema.array(String).default(['base']) })",
    }]
    const schema = executeSchemaSources(arraySources, "arrays")
    const defaults = createDefaultModel(schema)

    expect(defaults).not.toHaveProperty("tags")
    expect(defaults.names).toEqual(["base"])
  })

  it("exposes schema capabilities and task metadata", () => {
    const capabilitySources = [{
      name: "klein",
      hash: "klein",
      schema: `Schema.object({
        task: Schema.union(['text-to-image', 'image-edit']).default('text-to-image'),
        train_data_dir: Schema.string(),
        control_data_dirs: Schema.array(String).role('paired-directories'),
      }).role('training-schema', { capabilities: ['lora', 'text-to-image', 'image-edit'], task: 'text-to-image' })`,
    }]
    const schema = executeSchemaSources(capabilitySources, "klein")

    expect(schema.capabilities).toEqual(["lora", "text-to-image", "image-edit"])
    expect(schema.task).toBe("text-to-image")
    expect(schema.sections.flatMap((section) => section.fields).find((field) => field.key === "control_data_dirs")?.role)
      .toBe("paired-directories")
  })

  it("serializes task-specific reference directories only for image editing", () => {
    const capabilitySources = [{
      name: "klein",
      hash: "klein",
      schema: `Schema.intersect([
        Schema.object({
          task: Schema.union(['text-to-image', 'image-edit']).default('text-to-image'),
          train_data_dir: Schema.string(),
        }),
        Schema.union([
          Schema.object({
            task: Schema.const('image-edit').required(),
            control_data_dirs: Schema.array(String).role('paired-directories'),
          }),
          Schema.object({ task: Schema.const('text-to-image') }),
        ]),
      ])`,
    }]
    const schema = executeSchemaSources(capabilitySources, "klein")
    const model = { task: "text-to-image", train_data_dir: "./images", control_data_dirs: ["./controls"] }

    expect(serializeModel(schema, model)).not.toHaveProperty("control_data_dirs")
    expect(serializeModel(schema, { ...model, task: "image-edit" })).toMatchObject({
      control_data_dirs: ["./controls"],
    })
  })

  it("does not serialize blank paired reference directories", () => {
    const capabilitySources = [{
      name: "klein",
      hash: "klein",
      schema: `Schema.object({
        task: Schema.union(['text-to-image', 'image-edit']).default('image-edit'),
        control_data_dirs: Schema.array(String).role('paired-directories'),
      })`,
    }]
    const schema = executeSchemaSources(capabilitySources, "klein")

    expect(serializeModel(schema, { task: "image-edit", control_data_dirs: ["", "  ", "./controls"] }))
      .toMatchObject({ control_data_dirs: ["./controls"] })
  })

  it("orders sections by shared training groups", () => {
    const orderedSources = [{
      name: "ordered",
      hash: "ordered",
      schema: `Schema.intersect([
        Schema.object({ save: Schema.string() }).role('section', { group: 'save' }).description('保存设置'),
        Schema.object({ model: Schema.string() }).role('section', { group: 'model' }).description('训练用模型'),
        Schema.object({ dataset: Schema.string() }).role('section', { group: 'dataset' }).description('数据集设置'),
      ])`,
    }]
    const schema = executeSchemaSources(orderedSources, "ordered")

    expect(schema.sections.map((section) => section.title)).toEqual(["训练用模型", "数据集设置", "保存设置"])
  })

  it("clones array defaults for new models", () => {
    const arraySources = [{
      name: "arrays",
      hash: "arrays",
      schema: "Schema.object({ tags: Schema.array(String).default(['base']) })",
    }]
    const schema = executeSchemaSources(arraySources, "arrays")
    const first = createDefaultModel(schema)
    ;(first.tags as string[]).push("changed")

    expect(createDefaultModel(schema).tags).toEqual(["base"])
  })

  it("executes every backend training schema", () => {
    const schemaDir = resolve(process.cwd(), "../mikazuki/schema")
    const realSources = readdirSync(schemaDir).filter((name) => name.endsWith(".ts")).map((file) => ({
      name: file.slice(0, -3),
      hash: file,
      schema: readFileSync(resolve(schemaDir, file), "utf8"),
    }))
    for (const source of realSources.filter((item) => item.name !== "shared")) {
      const schema = executeSchemaSources(realSources, source.name)
      expect(schema.sections.length, source.name).toBeGreaterThan(0)
      expect(Object.keys(createDefaultModel(schema)).length, source.name).toBeGreaterThan(0)
    }

    const master = executeSchemaSources(realSources, "lora-master")
    const trainTypeFields = master.sections.flatMap((section) => section.fields).filter((field) => field.key === "model_train_type")
    expect(trainTypeFields).toHaveLength(1)
    expect(trainTypeFields[0].options).toEqual(["sd-lora", "sdxl-lora"])
    expect(serializeModel(master, createDefaultModel(master))).toMatchObject({
      model_train_type: "sdxl-lora",
      network_module: "networks.lora",
    })

    const flux = executeSchemaSources(realSources, "flux-lora")
    expect(serializeModel(flux, createDefaultModel(flux))).toMatchObject({
      model_train_type: "flux-lora",
      model_type: "flux",
      network_module: "networks.lora_flux",
    })

    const anima = executeSchemaSources(realSources, "sd3-lora")
    const animaModel = createDefaultModel(anima)
    const expectedModules = {
      lora: "networks.lora_anima",
      lokr: "lycoris.kohya",
      tlora: "networks.tlora_anima",
      lora_fa: "networks.lora_anima",
      vera: "networks.lora_anima",
      loha: "networks.loha",
    }
    for (const [loraType, networkModule] of Object.entries(expectedModules)) {
      animaModel.lora_type = loraType
      expect(serializeModel(anima, animaModel).network_module, loraType).toBe(networkModule)
    }

    const animaFast = executeSchemaSources(realSources, "anima-lora-fast")
    expect(serializeModel(animaFast, createDefaultModel(animaFast))).toMatchObject({
      lora_type: "lora",
      method: "lora",
      methods_subdir: "gui-methods",
      network_module: "networks.lora_anima",
    })

    const klein = executeSchemaSources(realSources, "klein-lora")
    expect(klein.capabilities).toEqual(["lora", "text-to-image", "image-edit"])
    const modelFields = klein.sections.find((section) => section.title === "训练用模型")!.fields
    expect(modelFields.find((field) => field.key === "model_source")).toMatchObject({
      role: "model-source-selector",
      defaultValue: "local-file",
      options: ["local-file", "local-directory", "hf-repo"],
    })
    expect(modelFields.find((field) => field.key === "dit")?.role).toBe("model-path")
    expect(modelFields.find((field) => field.key === "vae_source")).toMatchObject({
      role: "vae-source-selector",
      defaultValue: "follow-dit",
      options: ["follow-dit", "custom"],
    })
    expect(klein.sections.map((section) => section.title)).toEqual([
      "训练用模型",
      "训练模型类型",
      "数据集设置",
      "保存设置",
      "训练过程",
      "学习率与优化器",
      "网络设置",
      "训练预览图设置",
      "省显存",
      "日志 / caption / 噪声 / 数据增强",
      "其他",
    ])
    expect(klein.sections.flatMap((section) => section.fields).find((field) => field.key === "task")?.role)
      .toBe("task-selector")
    const memoryFields = klein.sections.find((section) => section.title === "省显存")!.fields
    expect(memoryFields.map((field) => field.key)).toEqual([
      "quantize",
      "quantize_te",
      "qtype",
      "qtype_te",
      "low_vram",
      "layer_offloading",
    ])
    expect(memoryFields.find((field) => field.key === "low_vram")?.defaultValue).toBe(true)
    expect(klein.sections.flatMap((section) => section.fields).some((field) => field.key === "prompt_file"))
      .toBe(false)
    const kleinDefaults = createDefaultModel(klein)
    expect(kleinDefaults.train_data_dir).toBe("./train/data")
    const datasetFields = klein.sections.find((section) => section.title === "数据集设置")!.fields
    expect(datasetFields.map((field) => field.key).slice(0, 3)).toEqual([
      "task",
      "train_data_dir",
      "control_data_dirs",
    ])
    const resolution = datasetFields.find((field) => field.key === "resolution")!
    expect(resolution.type).toBe("array")
    expect(resolution.role).toBe("resolution-selector")
    expect(resolution.defaultValue).toEqual([512, 768, 1024])
    expect(datasetFields.find((field) => field.key === "dataset_repeats")?.defaultValue).toBe(1)
    expect(serializeModel(klein, kleinDefaults)).not.toHaveProperty("control_data_dirs")
    expect(serializeModel(klein, { ...kleinDefaults, task: "image-edit", control_data_dirs: ["./controls"] }))
      .toHaveProperty("control_data_dirs", ["./controls"])
  })
})
