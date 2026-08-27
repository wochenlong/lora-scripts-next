# 安装期补丁（unified diff）

每个补丁一个 `.diff` 文件，并在 manifest 的 `PATCHES` 清单登记。
安装流程：`git apply --check` 先验证，打不上**响亮失败**（禁止静默跳过）；
打完后文件名记入快照目录的 `.applied_patches`，并随 audit 溯源。

## 补丁头格式（必填注释行）

```text
# target: <上游相对路径>
# symptom: <不打这个补丁会发生什么>
# removal: <摘除条件：上游修了什么 PR/版本后可删>
# source: <坑的来源，FIELD_NOTES 或 KNOWN_PITFALLS 条目>
```

程序性替换（如 pyproject 依赖改写）不适合 diff 时，写在 `environment.py`
并在本 README 登记同样的四要素。
