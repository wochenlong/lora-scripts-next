"""adapter.py stub — UI 配置 → 引擎原生配置。

职责：把 UI 提交 dict 映射为引擎原生配置（字段白名单 + 改名 + 默认值），
提供 dump_*_toml。映射表按 docs/design/training-param-glossary.md（#300）对齐，
语义不等价项禁止硬并。
输入：UI config dict + RuntimeConfig + run_id；
输出：Adapted(values, dataset, warnings)（结构自定，run.py 消费）。
完成判据：UI 配置能 dumps 出引擎原生配置；不支持的字段响亮报错而非静默丢弃。
参考：mikazuki/engines/musubi/adapter.py（SUPPORTED_FIELDS 白名单范式）。
"""
