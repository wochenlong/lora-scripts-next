"""installer.py stub — 源码快照与安装计划。

职责：把上游源码（zip 包 / git clone / 本地目录）抽成安装输入，
构建 InstallPlan（源 → 目标布局），提供 copy_source_snapshot / remove_extension。
钉版：git archive <commit> 或 zip 快照，装完写 .source_commit。
输入：source_root + layout + source_commit；输出：InstallPlan（as_dict 可序列化）。
完成判据：dry_run 能打印计划；真实安装后目标目录含 .source_commit。
参考：mikazuki/engines/musubi/installer.py。
"""
