# 设计约定 — 图像编辑训练数据集前端契约

> **状态**：产品已拍板（2026-08-26）；本文只定**前端 / 磁盘契约**，引擎 adapter 另开实施。  
> **关联**：[#252](https://github.com/wochenlong/lora-scripts-next/issues/252)（图像编辑训练 UI）；分区排序见 [`training-form-section-order.md`](./training-form-section-order.md)；引擎 [#284](https://github.com/wochenlong/lora-scripts-next/issues/284) / Klein [#299](https://github.com/wochenlong/lora-scripts-next/issues/299)。  
> **参考**：AI Toolkit 工作台 Target Dataset + Control Dataset（多目录同名配对）。

---

## 1. 产品口径（一句话）

**不**加「文生图 / 图像编辑」模式切换。只在 **数据集设置** 里用路径是否填写来分流；磁盘布局与 **AI Toolkit 图像编辑数据集格式**对齐。

**引擎取向（2026-08-26）**：该契约的**首要消费者是 AI Toolkit**（下版本接入，后端先行）。Klein **不**再规划挂到 Musubi；其它引擎若日后消费同一磁盘布局，由各自 adapter 转换，前端不改第二套格式。

---

## 2. 前端字段契约

| 字段 | 类型 | 含义 |
|------|------|------|
| `train_data_dir` | `string`（必填） | **目标图**目录：要学成的图；caption 与目标图同名放此目录 |
| `control_data_dirs` | `string[]`（可选） | **参考图**目录列表；与 AI Toolkit 多 Control 目录对齐 |

### 2.1 任务判定（勿另开 task / tab）

```text
control_data_dirs 全空（或未出现）     → 文生图（无 input）
control_data_dirs 有 ≥1 个非空路径     → 图像编辑（参考张数 = 非空路径数）
```

说明：

- 无论文生图还是编辑，都**继续使用** `train_data_dir` 作为主数据集路径；**不要**把「出现了 `train_data_dir`」理解成「只能文生图」。
- 单参考 = 数组长度 1；多参考 = 多个目录。不要并列维护互斥的单字段 `control_data_dir` 与另一套多路径 API。

### 2.2 UI 形态

- 数据集分区内：目标图路径（现有 filepicker）+「参考图目录 1 / 2 / …」可添加（建议默认最多展示/限制与引擎 capability 对齐，第一版可先 **最多 3** 路，与 AI Toolkit UI 一致）。
- 文案提示：参考图与目标图 **同名配对**（扩展名可不同）；**参考图不需要 caption**；不填参考图则按文生图训练。
- 训练预览：仅当存在参考图时，预览项可挂对应 control 图（细节随引擎实施）。

### 2.3 明确不做（首期）

- 「文生图 / 图像编辑」Tab 或第四维 `task` 切换。
- Dataset 工作台内的配对浏览 / 拖拽对齐 UI（仍按 [#252](https://github.com/wochenlong/lora-scripts-next/issues/252)：训练页填路径即可）。
- 为其它引擎单独做第二套前端目录布局（一律 AI Toolkit 多目录契约）。

---

## 3. 磁盘格式（与 AI Toolkit 对齐）

用户准备的数据应为：

```text
targets/                 ← train_data_dir
  photo001.png
  photo001.txt           # caption / 编辑指令
refs_a/                  ← control_data_dirs[0]
  photo001.png           # 与目标同名，扩展名可不同
refs_b/                  ← control_data_dirs[1]（多参考时）
  photo001.png
```

配对规则：各 `control_data_dirs[i]` 内按 **basename 与目标图一致** 查找；找不到则提交前校验失败（或按产品后续规定抽样报错），禁止静默丢参考。

---

## 4. 引擎职责（预期，非本文实现）

| 引擎 | 预期 |
|------|------|
| **AI Toolkit（首选）** | 前端字段几乎直通：`train_data_dir` → target/`folder_path`；`control_data_dirs` → `control_path` 列表（见 #284 / #299） |
| **其它引擎（可选）** | 若消费同一磁盘布局，adapter 自行映射；**不**为 Klein 单独往 Musubi 再叠一套编辑栈 |

上限、是否允许 0 张参考（Klein 可无 control；部分模型强制 control）由引擎 **capability** 下发或文档约定；前端按 capability 做必填/张数校验，不硬编码死在某一个模型名上（首期实现可先写死 Klein/Kontext 表，再收拢）。

---

## 5. 与分区排序的关系

图像编辑**只扩展「数据集设置」**（及必要时「训练预览图设置」的 control 图），**不**新增「×× 专用 / 编辑」大分区。全站顺序仍以 [`training-form-section-order.md`](./training-form-section-order.md) 为准。

---

## 6. 落地清单（后续实施 PR）

- [ ] Schema：对支持编辑的模型（如 Klein）在数据集区增加 `control_data_dirs`（数组 + filepicker）
- [ ] 文案 / i18n：目标图 vs 参考图；同名配对说明
- [ ] 提交前轻量校验：目录存在、抽样同名配对
- [ ] AI Toolkit 引擎 + adapter：直通同一字段（#284 / #299，**后端先行**）
- [ ] 预览路径挂 control（有参考图时）

协作：引擎 / 后端 [@MikumikuDAIFans](https://github.com/MikumikuDAIFans)、[@IryNeko](https://github.com/IryNeko)；产品 / 前端 [@wochenlong](https://github.com/wochenlong)。
