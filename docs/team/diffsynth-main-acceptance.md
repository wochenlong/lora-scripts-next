# DiffSynth main integration acceptance

Local validation on 2026-09-22 (Asia/Shanghai), source commit `21ccf015`.
This is a functional smoke test, not a convergence or image-quality benchmark.

## Training

- Windows, NVIDIA RTX 4090 24 GB; Python 3.12, PyTorch 2.8 CUDA 12.8.
- Used the main-based PR #372 adapter and launcher with the existing isolated
  DiffSynth environment. Added its declared dependencies `bitsandbytes==0.48.2`
  and `opencv-python-headless==4.11.0.86`; this was not a clean installation test.
- Comfy-Org Qwen-Image-2.1 BF16 DiT, Qwen3-VL-8B BF16 text encoder and BF16 VAE.
- Five local example images with CSV captions; 256x256 buckets, batch size 1,
  one epoch, rank/alpha 4, AdamW8bit, learning rate 0.0001.
- TE/VAE encoding caches enabled. Ran CPU offload enabled and disabled separately.
- Both runs exited 0 after five optimizer updates, generated previews at updates
  2 and 4, continued to update 5 and saved checkpoints for updates 1 through 5.
- Local logs: `.runtime/offload-on.log` and `.runtime/offload-off.log` in the
  `diffsynth-qwen21-main` worktree. Configs and outputs remain under `.runtime`;
  model weights, datasets and generated checkpoints are not committed.

## Independent ComfyUI reload

- Separate ComfyUI checkout at
  `b0f4b7b294ce482a2e071d9d762c133d38c7aa07`; existing user installations unchanged.
- Loaded original Comfy-Org BF16 components and the offload-disabled run's
  step-5 LoRA through ComfyUI's actual model/LoRA loading APIs.
- LoRA applied to 192 model patch entries. Executed ComfyUI sampling (Euler,
  simple schedule, 4 steps, CFG 4, seed 42) and VAE decoding.
- Exit 0; finite output, saved 256x256 RGBA PNG with pixel standard deviation
  approximately 0.318. This was a command-line ComfyUI API test, not a browser
  workflow test or a claim of trained visual quality.
- Local repository-root artifacts: `.runtime/comfy-qwen21-smoke.py`,
  `.runtime/comfy-qwen21-smoke.log`, `.runtime/comfy-qwen21-lora.png`.
- ComfyUI reported a newer-CUDA optimization warning; the tested CUDA 12.8 path
  nevertheless completed sampling and decoding.

## Other checks and limits

- 29 targeted frontend tests passed; typecheck and production build passed.
- Selected backend tests: 8 passed, 1 skipped. Full backend regression was not
  run; some inherited tests still encode the earlier Processor behavior.
- No image-edit training, quantized training, full-state resume, long training,
  multi-GPU, clean-install or browser stop/resume acceptance is claimed.
- Does not close the broader #290 requirements.
