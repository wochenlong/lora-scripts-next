# Anima Fast 模式 — 合并前检查清单

面向维护者：在将 `integrate-anima-fast` 合并进 `main` 前核对下列项。

## 1. 许可证与归属

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `NOTICE.md` 含 `sorryhyun/anima_lora` MIT 声明 | ✅ | 章节「Anima LoRA Fast Mode」 |
| 插件安装复制上游 `LICENSE` / `NOTICE` | ✅ | `installer.py` → `INCLUDE_TOP_LEVEL` |
| 用户文档致谢与仓库链接 | ✅ | `docs/anima-fast.md` §致谢；Fast 页 `anima-fast-credit` |
| 本仓库 AGPL 与 upstream MIT 兼容 | ✅ | MIT 可嵌入；插件以独立目录分发，不修改上游许可 |
| Automagic 等移植代码文件头 MIT 注明 | ✅ | `extensions/anima_lora/source/library/training/optimizers/`（插件快照内） |

**关于是否告知上游作者**：MIT **不要求**事先征得作者同意；合规要点是**保留版权与许可声明**并在产品中**醒目致谢**（本仓已在 `NOTICE.md`、Fast 页、用户文档完成）。向 [sorryhyun/anima_lora](https://github.com/sorryhyun/anima_lora) 开 Discussion/Issue 仅为**礼节性可选**，作者若未回复也不影响合入与发布。

## 2. 用户安装与说明文档

| 文档 | 用途 |
|------|------|
| [`docs/anima-fast.md`](anima-fast.md) | **主文档**：安装、训练、API、故障排除、性能、许可 |
| [`docs/anima-training.md`](anima-training.md) | 标准 Anima LoRA；文末链接 Fast |
| [`docs/examples/anima-lora-benchmark-*.toml`](examples/) | 可复现对标配置 |
| Fast 页 `/lora/anima-fast.html` | 页内安装引导 + 开源致谢 |
| `assets/readme/screenshot-anima-fast.png` | README / `docs/anima-fast.md` 界面截图 |

**用户路径**：`run_gui.bat` → **Anima LoRA → Fast 模式** → **开启插件** → **开始训练**。

## 3. 性能数据（同参对标）

详见 [`docs/anima-fast.md` §性能对比`](anima-fast.md#性能对比本仓库实测)。摘要：

- **环境**：RTX 4090 24GB，Windows，数据集 `data/train_data/10_subject`（10 张，1024 bucket）
- **共用参数**：LoRA dim/alpha=16，AdamW lr=1e-4，batch=1，bf16，gradient_checkpointing，无 latent cache
- **标准模式**（Kohya，`attn_mode=sdpa`）：**≈7.1 s/step**（20 step 共 2分22秒）
- **Fast 模式**（anima_lora，`attn_mode=flash`，本次未开 compile）：**≈2.8 s/step**（50 step 稳态）→ **约 2.5×**
- **Fast 默认**（UI `torch_compile=true`）：编译预热后通常更快；上游在 RTX 5060 Ti 报告 **≈1.1 s/step**（rank 32，1MP，full compile）

复现命令见 `docs/anima-fast.md` §复现对标训练。

## 4. 合并前自测

- [ ] `python -m unittest tests.test_anima_fast_* tests.test_train_monitor_status -v`
- [ ] Fast 页插件安装 → 状态「插件已就绪」
- [ ] 短训 smoke（1 epoch）+ 训练监控 Loss/进度/预览
- [ ] `NOTICE.md` / `docs/anima-fast.md` 链接在 README 文档表可见

## 5. PR 前仍待补齐（发版前）

| 项 | 状态 | 说明 |
|----|------|------|
| `CHANGELOG.md` + `VERSION` → **v2.7.0** | ✅ | |
| `scripts/patch-home-changelog.py` 重生首页/更新日志页 | ✅ | 含 v2.7.0 + Fast 首页链接 |
| 未提交改动一次性 commit | ✅ | 本 PR |
| `docs/repo-layout.md` 补充 `extensions/anima_lora/`、`config/anima_fast_*` | ✅ | |
| 整合包说明：Fast **不预装**插件 venv | ✅ | `docs/portable-packaging-git-update.md`、`build-scripts/README.md` |
| 正式 PR 描述（见 §6） | ✅ | 复制 §6 到 PR body |
| `CONTRIBUTORS.md` @MikumikuDAIFans | ✅ | |
| 上游 anima_lora Discussion 告知 | ⏭ 可选 | MIT 已合规；非阻塞 |
| Fast + `torch_compile=true` 对标日志补一条 | ⏭ 可选 | 现有 2.5× 为 compile 关闭对照 |

## 6. PR 描述模板（复制到 GitHub PR body）

```markdown
## Summary

- 集成 **Anima LoRA Fast 模式**（可选插件 [sorryhyun/anima_lora](https://github.com/sorryhyun/anima_lora)，MIT）：页内安装、独立 cu130 venv、`anima-lora-fast` 训练路由。
- 训练监控：Fast Loss / ETA / Epoch、`*.progress.jsonl` 与预览图按活动任务 output 同步。
- 文档、NOTICE、benchmark 示例与 v2.7.0 发版条目；整合包**不预装**插件 venv。

## 用户路径

`run_gui.bat` → **Anima LoRA → Fast 模式** → **开启插件** → 填参 → **开始训练**  
主文档：[`docs/anima-fast.md`](docs/anima-fast.md)  
合并前清单：[`docs/anima-fast-merge-checklist.md`](docs/anima-fast-merge-checklist.md)

## 性能（RTX 4090，同参 10 张 / 1024 / LoRA 16）

| 模式 | 稳态 step | 相对 |
|------|-----------|------|
| 标准 Kohya（sdpa） | ≈7.1 s/step | 1× |
| Fast（flash，compile 关） | ≈2.8 s/step | **≈2.5×** |

复现：`docs/examples/anima-lora-benchmark-{kohya,fast,dataset}.toml`

## 环境变量

- `LORA_ENABLE_ANIMA_FAST=1`（默认）：显示 Fast 入口与 API；`0` 隐藏。

## Test plan

- [ ] `python -m unittest tests.test_anima_fast_* tests.test_train_monitor_status -v`
- [ ] Fast 页安装插件 → 「插件已就绪」
- [ ] 短训 1 epoch + 训练监控 Loss/预览
- [ ] 侧栏版本号显示 **2.7.0**
```
