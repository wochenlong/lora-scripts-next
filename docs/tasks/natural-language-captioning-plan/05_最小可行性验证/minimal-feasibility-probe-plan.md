# 最小可行性验证计划

## 已完成 P1

- SiliconFlow Qwen3.6-27B：三张中文 strict JSON、data URL、stream cancel、cancel 后恢复。
- Qwen3-VL-2B Q4 + Q8 mmproj：Windows CPU-only 三张中文 strict JSON、资源占用、stream cancel、cancel 后恢复。
- SmolVLM-256M：英文低资源路径，中文失败边界已记录。

## Phase 0 前置探针

- v4 translation config → v5 profile migration fixture，要求幂等。
- fake text/vision server，模拟 JSON schema、429、timeout、invalid response。
- remote-first route matrix：remote ready, remote fail/local ready, both fail, translation text-only。

## Phase 1 探针

- 3 image fake caption job，验证 natural、cache、atomic writer。
- cancel after first completed image，验证已完成项保留。
- external file mutation，验证 caption_conflict。

## Phase 3 真实限制

- 不超过 20 张不敏感样本；
- 单次真实任务最长 15 分钟；
- 远程样本只使用公开或脱敏图；
- 输出放 evidence 目录，测试结束清理图片、model cache 和 raw response。

