# Anima Edit 单图参考 — 文档例图

> **对外发布请用精选例图**：[`../anima-edit-showcase-curated/`](../anima-edit-showcase-curated/)（AI ref + LoRA 推理）。  
> 流程见 [anima-edit-showcase-workflow.md](../../design/anima-edit-showcase-workflow.md)。  
> 本目录下 `hero-sample*` 来自 **ImagePulse 训练集前几条**，仅作管线验证，**不宜当官方门面图**。

单图参考：``reference/<stem>.png`` 与 ``target/<stem>.png`` **同名配对**，caption 在 ``target/<stem>.txt``。

## 目录说明

| 文件 | 含义 |
|------|------|
| `hero-*-ref.png` | 输入参考图（仅 1 张） |
| `hero-*-gt.png` | 训练目标图（Ground Truth） |
| `hero-*-out-e12.png` | e12 权重 + **完整训练 caption** 推理结果（已生成） |
| `layout.svg` / 拼图 | 可选，发布用 |

## 数据与训练

- 展示集：`data/anima-edit-single-showcase/`（32 对，由 ImagePulse 双参考集取 `reference/<stem>/1.png`）
- 构建：`python script/ops/build_anima_edit_single_ref_showcase.py`
- 训练示例：`docs/examples/anima-edit-single-ref-12epoch.toml`
- 预览 manifest：`docs/examples/anima-edit-single-ref-sample-prompts.toml`（**必须与训练 caption 一致**）

## 与双参考的区别

| | 单图参考 | 双图参考 |
|---|---------|---------|
| 参考目录 | `reference/foo.png` | `reference/foo/1.png`, `2.png` |
| 典型任务 | 单角色/物体 → 编辑结果 | 两参考 → 融合图 |
| dataset 标志 | 无 `conditioning_multi_reference` | `conditioning_multi_reference = true` |

双参考例图见 `docs/assets/anima-edit-dual-ref/`（待补）。
