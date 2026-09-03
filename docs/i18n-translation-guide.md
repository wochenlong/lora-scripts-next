# 前端国际化翻译指南

> 适用对象：为 `frontend/` 新增或校对语言资源的贡献者。
> 相关代码：`frontend/src/i18n/index.ts`（locale 注册表）、`frontend/src/i18n/messages/*.ts`（语言资源）、`frontend/src/i18n/index.test.ts`（一致性门禁）。

## 1. 支持语言与状态

当前注册的语言、状态和方向以 `frontend/src/i18n/index.ts` 中的 `SUPPORTED_LOCALES` 为唯一权威来源：

| Locale | 语言 | 状态 | 方向 |
| --- | --- | --- | --- |
| `zh-CN` | 简体中文 | stable | ltr |
| `en-US` | English | stable | ltr |
| `zh-TW` | 繁體中文（台灣） | beta | ltr |
| `zh-HK` | 繁體中文（香港） | beta | ltr |
| `ja-JP` | 日本語 | beta | ltr |
| `ko-KR` | 한국어 | beta | ltr |
| `es-ES` | Español | beta | ltr |
| `fr-FR` | Français | beta | ltr |
| `de-DE` | Deutsch | beta | ltr |
| `ru-RU` | Русский | beta | ltr |
| `pt-PT` | Português (Portugal) | beta | ltr |
| `pt-BR` | Português (Brasil) | beta | ltr |
| `ar` | العربية | beta | rtl |

- **stable**：经过母语校对、可直接发布。
- **beta**：机器翻译初稿或未经完整母语校对，设置页语言名旁会显示 `Beta`。beta 不阻止发布，欢迎社区持续校对。
- 每个语言的母语校对者/维护者请在本文件第 7 节登记。

## 2. 两个"基准"的区别

- **语义源：`en-US`**。新增或修改文案时以英文为准理解含义；英文是各语言翻译的对照基准。
- **运行时 fallback：`zh-CN`**。vue-i18n 的 `fallbackLocale` 是简体中文；任何语言缺失 key 时用户看到的是简体中文。未知浏览器语言同样回退到 `zh-CN`。

## 3. 不翻译词表

以下内容在所有语言中保持原文：

- 产品与项目名：Next Trainer、lora-scripts、sd-scripts。
- 模型与架构：LoRA、SD 1.5、SDXL、Flux、Anima / Anima DiT、Lumina 2、Krea 2、Klein、FLUX.2、VAE、CLIP、WD14。
- 训练引擎：Kohya-ss、Anima Fast、Musubi-Tuner、AI Toolkit。
- 优化器与调度器名：AdamW、Prodigy、DAdaptation 等；网络模块名 LyCORIS / LoKr / LoHa / DyLoRA。
- 技术格式与工具：TOML、TensorBoard、Schema、GPU、NVIDIA、pip、PyPI、PyTorch、uv、Hugging Face、ModelScope、GitHub、Civitai。
- 下载镜像与站点名：Tsinghua TUNA、Aliyun、Douban、BFSU、hf-mirror、ghfast.top、mirror.ghproxy.com。
- 配置 key（如 `unet_lr`、`lr_scheduler`）、命令行参数（`--n`、`--w/--h`、`--l`、`--s`、`--d`）、URL、文件路径、模型仓库 ID、许可证号（AGPL-3.0 / MIT / Apache-2.0）。
- 后端错误原文、训练日志、第三方脚本输出：**一律原样显示**，不纳入翻译资源，也不做错误码映射。

常用术语对照（翻译时保持一致）：

| 英语 | 简中 | 说明 |
| --- | --- | --- |
| training | 训练 | 日语用「学習」，韩语用「학습」 |
| epoch | 轮次 / epoch | 各语言统一选一种并保持一致 |
| batch size | 批次大小 | |
| learning rate | 学习率 | |
| checkpoint | checkpoint | 不译 |
| preset | 预设 | |
| schema | Schema | 指后端动态表单 schema |
| caption | 打标文本 / caption | 数据集语境 |
| tag | 标签 | |
| audit | 审计 | 引擎安装后的环境审计 |
| runtime | 运行时 | 指独立 Python 运行环境 |

## 4. 新增或修改文案的流程

所有语言的 key 集合和插值参数由测试强制对齐，漏 key 会直接失败：

1. 修改 `en-US.ts` 与 `zh-CN.ts`（二者是 stable，必须同步更新）。
2. 其余 beta 语言同步补同 key 的翻译；占位符 `{n}`、`{label}`、`{min}`、`{max}` 等**名称与数量必须完全一致**，不翻译占位符名称。
3. 运行一致性检查：

```bash
cd frontend
npx vitest run src/i18n/index.test.ts
npm run typecheck
```

提交前执行完整检查 `npm run check`（typecheck + ESLint + Vitest + 生产构建），与 `package.json` 的 scripts 保持一致。

## 5. 新增一个语言的注册步骤

1. 在 `frontend/src/i18n/messages/` 新建 `<locale>.ts`，完整翻译全部 key（以 `en-US.ts` 为语义源）。
2. 在 `frontend/src/i18n/index.ts` 中：
   - `SUPPORTED_LOCALES` 增加 `{ value, label, status: "beta", direction }`；`label` 使用该语言的本地写法（如 `Deutsch`），地区变体写全（如 `Português (Brasil)`）。
   - `localeMessages` 与 `elementPlusLocales` 同步增加条目；Element Plus 语言包以 `element-plus/es/locale/lang/` 实际 export 为准。
   - `LOCALE_MATCH_RULES` 增加浏览器语言匹配规则（精确地区优先，不用模糊 `startsWith` 覆盖所有地区）。
3. 在 `index.test.ts` 补充代表性匹配断言（如 `fr-CA → fr-FR`、`pt-AO → pt-PT`）。
4. 语言资源不完整时不要注册——`Record<AppLocale, ...>` 类型约束和遍历测试会直接阻止半成品进入语言选择器。
5. RTL 语言（如 `ar`）必须与 RTL 布局可用性同时上线，不能先暴露语言再补布局。

## 6. 地区变体必须独立维护

- `zh-TW` / `zh-HK`、`pt-PT` / `pt-BR` 使用**各自完整的资源文件**，即使首期内容相同，也不允许 import、spread 或 re-export 复用，保证后续独立演进。
- AI 翻译只能作为初稿。beta 语言转 stable 的建议条件：
  1. 核心页面（设置、训练、任务、数据集）完成母语者校对；
  2. 无缺失 key、插值参数全部一致；
  3. 至少一次桌面端与移动端（窄屏）冒烟；
  4. 术语表无未决高频分歧词。
- 完成校对后在 `SUPPORTED_LOCALES` 中把 `status` 改为 `"stable"`，并在 PR 描述中注明校对范围。

## 7. 校对者登记

| Locale | 状态 | 最近校对 | 校对者 |
| --- | --- | --- | --- |
| zh-CN | stable | 持续 | 核心维护者 |
| en-US | stable | 持续 | 核心维护者 |
| 其余语言 | beta | 机器初稿，待母语校对 | 待登记 |

## 8. 边界

- 后端返回的错误文本、训练日志、命令输出保持原文，前端不做改写或翻译。
- 代码、日志、路径、TOML 预览、图表坐标在 RTL 语言下显式保持 LTR（见 `frontend/src/styles/` 中的 `direction: ltr` 保护）。
