"""/api/run handler — 五段式流水线的挂载点。

职责：接收 UI 提交的配置，按 gate → adapt → preflight → dump → launch 的顺序
组织本引擎的提交流水线。各段签名由各引擎自定（上游脚本奇形怪状是正常的），
框架只固定入口签名。

输入：config（UI 提交的 dict，已 pop 掉 model_train_type/gpu_ids），
     ctx: RunContext(timestamp, autosave_dir, gpu_ids, model_train_type)。
输出：APIResponseSuccess / APIResponseFail（mikazuki.app.models）。
完成判据：POST /api/run 带你的 train_type 能走到 handle_run 并返回结构化响应。
参考实现：mikazuki/engines/musubi/run.py（含 sample prompts 横向逻辑）、
         mikazuki/engines/anima_fast/run.py（含 ready gate + audit 漂移检测）。
"""

from mikazuki.app.models import APIResponseFail
from mikazuki.engines.runner import RunContext


def handle_run(config: dict, ctx: RunContext):
    # 1. gate：feature flag + 安装状态/audit 检查，未就绪返回明确错误。
    # 2. adapt：config -> 引擎原生配置（adapter.py）。
    # 3. preflight：资产/环境检查（preflight.py），失败要列出缺什么。
    # 4. dump：写 autosave TOML/dataset 文件到 ctx.autosave_dir。
    # 5. launch：交给 mikazuki.process 起任务，返回 task_id。
    return APIResponseFail(message="not implemented")
