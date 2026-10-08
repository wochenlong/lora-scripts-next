# feat/tagger-progress-ui → main 合并实测报告

> **日期**：2026-05-27  
> **分支**：`feat/tagger-progress-ui`（已 rebase `main`）  
> **执行环境**：Windows 10，Python 3.10，RTX 4090，huggingface-hub 0.36.2  

---

## 1. 结论

| 项 | 状态 |
|----|------|
| tqdm 阻断（模型下载进度） | **已修复并验证** |
| 真实打标 E2E（2 图 → `.txt`） | **通过** |
| rebase `main` + 重打 patch | **完成** |
| 可合并 `main`（打标进度 Phase 1） | **是**（见 §6 残留项） |

---

## 2. 修复内容：tqdm / huggingface-hub 0.36

### 现象

`POST /api/interrogate` 在需下载模型时 `phase=error`：

```text
type object 'tqdm' has no attribute 'tqdm'
```

### 根因

`model_fetch._hub_download_progress` 使用 `import huggingface_hub.utils.tqdm as m` 时，Python 绑定到 **tqdm 类**而非子模块；对 `m.tqdm` 赋值失败。  
`hf_hub_download` 实际使用 `huggingface_hub.utils.tqdm` **子模块**内的 `tqdm` 类及 `utils.tqdm` 再导出。

### 修复（`mikazuki/tagger/model_fetch.py`）

- 通过 `sys.modules["huggingface_hub.utils.tqdm"]` 取得真实子模块  
- 同时 patch `hf_tqdm_module.tqdm` 与 `huggingface_hub.utils.tqdm`  
- 提交：`ee735c0` → rebase 后为当前分支顶端之一  

### 验证

- 冷启动下载 WD `wd14-convnextv2-v2`：下载进度 **2/2 文件** 正常  
- 不再出现 tqdm 相关异常  

---

## 3. 真实打标 E2E

### 命令

```powershell
python script/scratch/e2e_tagger_run.py
```

（内部：`TestClient` + `POST /api/interrogate`，数据集为 `assets/logo.png`、`assets/cover.png` 的临时副本。）

### 结果

| 步骤 | 结果 |
|------|------|
| 模型下载（若未缓存） | 成功 |
| `phase` 流转 | `downloading` → `tagging` → **`done`** |
| 进度 | `tag=2/2` |
| 输出 | `cover.txt`、`logo.txt` 已生成，含 WD 标签 |

### 环境说明

本机最初因 **onnxruntime 1.23** DLL 加载失败导致打标中断（与 tqdm 无关）。  
将 onnxruntime 降为 **1.17.1** 后 E2E 通过。整合包/项目若已固定 ORT 版本则不受影响；建议在 README 打标 FAQ 中注明推荐 `onnxruntime==1.17.1`（与 `scripts/dev/requirements.txt` 注释一致）。

---

## 4. rebase `main` 与 patch

### rebase

```text
git rebase main
```

- **冲突**：约 20 个 `frontend/dist/**/*.html`、`gui.py`、`sd-trainer-brand.js`、`style.874872ce.css`、`patch-ui-brand-version.py`  
- **策略**：dist / `gui.py` / brand 相关 **取 main（ours）**，保留 feat 的后端与 `tagger-progress.js` 等新文件  
- **结果**：`Successfully rebased`，2 commits（feat + tqdm fix）  

### 重打 patch（rebase 后执行）

```powershell
python scripts/patch-tagger-progress-ui.py
python scripts/patch-spa-frontend-cache.py
python scripts/patch-ui-brand-version.py
```

| 脚本 | 作用 |
|------|------|
| `patch-tagger-progress-ui.py` | `tagger.html` 注入 `tagger-progress.js`；同步 `.sd-tagger-dock` CSS 到 `style.874872ce.css` |
| `patch-spa-frontend-cache.py` | HTML 缓存破坏版本号 |
| `patch-ui-brand-version.py` | 侧栏版本 chip（main 已有则 0 文件变更） |

**确认**：`frontend/dist/tagger.html` 含缓存参数化资源引用（版本 + 文件时间戳），例如：  
`<script src="/assets/tagger-progress.js?v=2.5.3-<mtime>" defer></script>`  
`<link rel="stylesheet" href="/assets/style.874872ce.css?v=2.5.3-<mtime>">`

### 未纳入本次 rebase 的 dist 变更

`main` 上 **Anima Edit / 帮助页传送门** 等（`anima-edit` 分支）不在本 feat 分支；合并 tagger PR **不会** 带回那些前端改动。

---

## 5. 自动化测试

新增 `tests/test_tagger_progress_api.py`：

- `GET /api/tagger/status` idle  
- busy 时 `POST /api/tagger/prefetch` 拒绝  
- `tagger.html` 含 `tagger-progress.js`  

```powershell
python -m pytest tests/test_tagger_progress_api.py -q
```

（不依赖 ONNX，适合 CI。）

---

## 6. 合并 main 前检查清单

| # | 项 | 状态 |
|---|-----|------|
| 1 | tqdm / 下载进度 | ✅ |
| 2 | 真实打标 E2E | ✅（本机 ORT 1.17.1） |
| 3 | rebase main | ✅ |
| 4 | patch 脚本已跑 | ✅ |
| 5 | API 单测 | ✅ 已补最小集 |
| 6 | 浏览器手点「启动」看底部坞 | ⬜ 建议合并前人工点一次 |
| 7 | Issue #40 全文（NL/Gemini/mode） | ⬜ 不在本 PR，另开 |
| 8 | 整合包 `build_portable` 验证 | ⬜ 合并后或 PR 说明中安排 |

---

## 7. 建议 PR 范围说明

**标题示例**：`feat(tagger): progress UI + download/tagging status API`

**包含**：

- 后端：`progress.py`、`jobs.py`、`model_fetch.py`、API 路由  
- 前端：`tagger-progress.js`、`sd-trainer-ui-polish.css`（dock 段）、`tagger.html` patch  
- 文档：`docs/design/tagger-progress-ui.md`、`docs/api/dataset-tagging.md`  
- 测试：`tests/test_tagger_progress_api.py`  

**不包含**：Anima Edit、帮助页、训练监控大改（留在其他分支）。

---

## 8. 提交记录（rebase 后）

```text
git log main..feat/tagger-progress-ui --oneline
```

预期 2 条：

1. `feat(tagger): add progress-aware tagging workflow`  
2. `fix(tagger): patch huggingface_hub tqdm for download progress on hf>=0.36`  

另含 **未提交** 的 patch 产物与测试、本报告（合并 PR 前需 `git add` dist + tests + docs）。

---

## 9. 复现命令速查

```powershell
git checkout feat/tagger-progress-ui
python scripts/patch-tagger-progress-ui.py
python scripts/patch-spa-frontend-cache.py
python -m pytest tests/test_tagger_progress_api.py -q
python script/scratch/e2e_tagger_run.py
python gui.py
# 浏览器打开 http://127.0.0.1:28000/tagger.html
```
