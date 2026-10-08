# 原goal完成后的全新手动测试项目交付

日期：2026-10-09。用户要求先完成goal，再在已清空的sandboxes中建立全新项目供最后手动测试。

执行顺序符合要求：清理闭门文档提交896e65a/c3b4a7f，update_goal返回complete，然后建立nl-caption-manual-20261009/project独立干净worktree，固定c3b4a7f（业务候选8986b9e）。原tests/test_diffsynth_review.py既有修改保留在开发树，没有进入新项目。新项目是用户明确要求留存的交付，不属于原五根清理剩余。

| 项目 | 实际结果 |
|---|---|
| 解释器/环境 | 新下载Python3.11.15、新venv；75个后端依赖新安装，torch2.7.0+cpu、onnxruntime1.26.0、FastAPI0.95.1 |
| 前端 | Node22.17.1、新npm缓存/依赖；typecheck和源构建通过 |
| 样本/模型 | 原冻结公开3图、Qwen3-VL-2B Q4_K_M/Q8 mmproj、WD ONNX、llama.cpp b11327全部新下载，8个源文件完整SHA和runtime exe SHA通过；HF镜像交付保留原始URL |
| 实际应用 | 正式FastAPI lifespan、独立state/user_data/config/SQLite/cache/queue/HF/模型目录；真实provider未替换 |
| 就绪检查 | 12项通过：模型安装、显式runtime启动、Qwen单图自然语言预览、WD单图Tag预览、两种预览零TXT写入、runtime停止、深链接访问等 |
| 实际浏览器 | 新BrowserContext，桌面及390px；无横向溢出、无pageerror，未配置API入口隐藏 |
| 重启检查 | 启动/停止脚本实际执行；config字节SHA相同、presets数据相同、本地模型/Profile保留，重启后模型停止 |
| 手测数据 | caption-samples与tag-samples各3公开图，均无TXT；启动检查只使用独立smoke目录 |
| 密钥 | 未预填Key；配置JSON扫描无Key格式；用户手测远程时自行通过共享LLM界面注入，重启需重输 |
| 留存/服务 | 保留全新项目；应用127.0.0.1:28766运行，本地视觉runtime停止；提供启动/停止cmd及ps1、中文README |
| 用户手动验收 | 等待用户自行测试，不把就绪检查写成人工最终通过 |

安装期间官方HF顺序流速度较慢，独立镜像并行传输成功且完整哈希一致；随后重复校验器发现runtime目录已存在，只读验证现有exe SHA后完成，不重复解包或重下载。该手测项目准备过程不冒充原Phase5的额外通过轮次。重启脚本第一次比较把旧HTTP包装与新data对象相比较，已修正同层比较；config和preset内容实际一致，未修改业务代码。

私有手测目录保留启动/安装日志、下载凭据、smoke报告和截图；公开证据仅记录摘要，不加入模型、样本、venv、node_modules、用户输出或绝对路径。没有Agent/plugin生产修改，没有发布/push。

用户下一步：运行start-manual-test.cmd或访问本机28766的/dataset/tagger，按README分别测试Caption、Tag、预设、任务与Editor；有远程视觉Profile时再测试远程优先/显式本地兜底。
