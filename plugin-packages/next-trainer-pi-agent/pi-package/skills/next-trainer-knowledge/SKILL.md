---
name: next-trainer-knowledge
description: 解答训练参数问题、解释参数含义与日志报错，并把任何训练建议建立在 Next Trainer 知识库与模板库之上。适用于"这个参数是干什么的 / 该设多少 / 这个报错什么意思 / 哪个模板合适"。Answer parameter questions, explain parameters and log errors, and ground any training recommendation in the Next Trainer knowledge base and template library. Use for "what does this parameter do / how much should I use / what does this error mean / which template fits".
---

# Next Trainer knowledge and parameter Q&A

Answer from evidence, not from memory. Before answering a parameter or template
question, inspect the bundled library with the `next_trainer_knowledge` tool:

1. `list` (optionally narrow with a `path` prefix such as `knowledge/` or `templates/`) to see what exists.
2. `search` with a topic keyword (e.g. `network_alpha`, `learning rate`, `diverge`) to locate relevant files.
3. `read` the specific file(s) you will rely on.

> **Single source of truth.** `next_trainer_knowledge` reads the data-root
> knowledge + templates — that is the user's library. Do NOT browse the
> plugin's own files (`plugins/next-trainer-pi-agent/...`, the SKILL.md and
> package source) with `read`/`find`/`bash` to answer a parameter question:
> that directory is the plugin's implementation, not the knowledge base, and
> its files may lag the data root. If the data-root library does not cover the
> question, say so — do not substitute the plugin's source files.

Cite only what you actually read. For every key claim give the relative file
path, the document `Version`, `Scope`, and `Evidence status` header. If the
library does not cover it, say so — do not invent a path, value, or conclusion.

## Answer types

- **Definition** — what the parameter controls.
- **Selection** — a suggested value *for the user's stated data + VRAM*, with the trade-off.
- **Interaction** — conflicts/links with cache, optimizer, network type, resolution.
- **Engine difference** — whether the same parameter is equivalent across kohya / anima-fast / musubi.
- **Error explanation** — what a log/traceback error usually means and the next check to run.

## Evidence discipline (three layers)

Label every answer with which layer it comes from:

1. Publicly disclosed fact — with a source path or URL.
2. Observed distribution — with sample size and missingness.
3. Model inference / proposed experiment — clearly labelled as such.

Popularity is discovery evidence only, never proof. Missing `trainingDetails`
stays unknown. Never start training from a template: a generated TOML draft must
pass `training_config_validate`, normalization, preflight, semantic diff, and
explicit user confirmation before import.

For structured retrieval over a set of documents you have already read, you may
call the host `knowledge_search` tool (it returns evidence-typed, versioned
excerpts with confidence).
