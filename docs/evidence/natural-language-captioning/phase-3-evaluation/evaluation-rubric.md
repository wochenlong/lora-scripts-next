# 冻结评测与人工评分规则 v1

样本为scikit-image v0.19.3公开资产3张，无用户图片；下载URL字节与冻结SHA256已实际核对，Phase3复制到独立eval样本目录。Phase4须重新下载并校验，不能复用此目录。来源和授权说明见[官方数据源码](https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/_fetchers.py)。参考事实由执行agent看图建立，是评分辅助，不是人工评分结果。

## 硬规则

每端3/3严格JSON、language=zh-CN、非空caption≤2000字、无Markdown/多余字段/重复键/NaN/截断；零本地绝对路径、EXIF或凭据外发；写回hash/atomic/conflict符合实现契约。任一违反均失败，不能以语句流畅抵消。

## 人工rubric（预先冻结，不在观察结果后降低）

| 维度 | 0分 | 2分 | 4分 |
|---|---|---|---|
| 主体正确 | 主体识别错 | 主体正确但泛化 | 主体准确明确 |
| 可见事实与幻觉 | 严重编造/身份故事 | 有可疑细节 | 仅可见且准确的事实 |
| 中文自然程度 | 不可读/语言错 | 可读但生硬 | 简洁流畅的中文 |
| 训练描述效用 | 与画面无关 | 有主体信息 | 主体+关键外观/空间关系 |
| 精简与指令服从 | 多余格式/冗长故事 | 重复或不必要推断 | 无重复且符合提示词 |

1/3分为相邻锚点之间。每张≤20分；每端均值≥16分且主体/事实两维每张≥3分，无严重幻觉。JSON硬规则与人工评分分别记录。

必须记录真实reviewer身份、时间、逐维分数和理由；未填为pending。机器规则/agent观察不得冒充人类评分。盲评可用A/B匿名组，然后解盲记录remote/local。质量未达标必须记录失败样本与revision，不能事后调低门槛。

baseline是先前P1探针的有限摘要，不伪造其未记录的评分；current是当前生产adapter/job产生的结果，二者字段不可比时注明missing，不补造。固定model/prompt/preprocess revision、temperature、max tokens、cache flags；比较caption长度/成功率/延迟/RSS和评分。

真实中文远程Qwen/Qwen3.6-27B与本地Qwen3-VL-2B均待current验收。SiliconFlow[当前官方接口](https://api-docs.siliconflow.cn/docs/api/chat-completions-post)声明视觉response_format支持json_schema/json_object；仍需当前adapter实际调用证明兼容。
