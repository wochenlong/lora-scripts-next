# DiffSynth 对症修复（#462）

> 状态：P0 已落地（diagnose + surgical repair + 完整重装拆分）。细节以 Issue [#462](https://github.com/wochenlong/lora-scripts-next/issues/462) 为准。

## 一句话

`POST /api/engines/diffsynth/repair` **默认不再整包重装**；先诊断，再只修损坏组件。整包重装必须显式 `action=full_reinstall`。

## 诊断

- `GET /api/engines/diffsynth/diagnose`
- `GET /api/engines/diffsynth/status` 在 `broken` / `not_installed` 时附带 `diagnosis`

## 修复动作

| action | 删除范围 |
|--------|----------|
| `refresh_state` | 无 |
| `repair_source` | 无（checkout / clone） |
| `repair_venv_deps` | 无（pip 重装） |
| `repair_venv` | 仅 `.venv` |
| `repair_python_runtime` | `.python` + `.venv` |
| `full_reinstall` | `.python` + `.venv` + `source` |

`host_no_gpu`：不推荐任何重装动作。
