# Qwen3-VL-2B 本地真实 smoke

- Asset source: existing P1 isolated probe sandbox
- Model: Qwen3VL-2B-Instruct-Q4_K_M.gguf
- mmproj: mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf
- Runtime: llama.cpp b11327, CPU-only, loopback OpenAI-compatible server
- Endpoint: loopback only; service stopped after the smoke
- Input: existing non-sensitive chelsea.png probe sample

## Result

- Unified LLM service reached the local endpoint.
- Request contained a JPEG data URL and no local path.
- Response parsed as strict JSON with exactly caption and language.
- language was zh-CN.
- Caption contained CJK characters.
- Markdown fences were absent.
- The local server was stopped after the check.

## Boundary

This proves the current adapter can consume the locked local Qwen profile. It does not replace the final 3–5 image evaluation, UI manual acceptance, or Phase 4 clean rebuild.
