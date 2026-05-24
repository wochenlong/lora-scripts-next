# Tagger CLI and OpenAI-Compatible API Captioning

This document covers the first command-line dataset tagging path for issue #40.
It does not change the WebUI tagger page and does not integrate the separate
dataset tag editor.

## Modes

### Local TAG mode

Local mode uses the existing WD/CL ONNX taggers in `mikazuki/tagger/` and writes
Danbooru-style TAG captions beside each image:

```powershell
python -m mikazuki.tagger.cli local --path .\input --model wd14-convnextv2-v2
```

```bash
python -m mikazuki.tagger.cli local --path ./input --model wd14-convnextv2-v2
```

Useful options:

- `--threshold 0.35`: general tag threshold.
- `--character-threshold 0.6`: character tag threshold.
- `--recursive`: scan child folders.
- `--additional-tags "masterpiece, best quality"`: always append tags.
- `--exclude-tags "lowres, bad anatomy"`: remove exact tags.
- `--use-cn-mirror`: use `https://hf-mirror.com` if the local model is missing.
- `--hf-endpoint https://...`: use a custom Hugging Face-compatible endpoint.
- `--on-conflict ignore|copy|prepend`: skip existing `.txt`, replace it, or
  prepend new tags to existing text.
- `--no-replace-underscore`: keep underscores in tags.
- `--no-escape-tag`: do not escape parentheses and backslashes.

Wrapper scripts are available:

```powershell
.\scripts\cli\tagger.ps1 local --path .\input
```

```bash
bash scripts/cli/tagger.sh local --path ./input
```

The wrappers only set `HF_HOME=huggingface`, prefer the local `venv` Python when
present, and forward all arguments to `python -m mikazuki.tagger.cli`.
The Python service also defaults `HF_HOME` to the project `huggingface/` folder
when the environment variable is not already set, so first-run model downloads do
not go to the user's global Hugging Face cache.
Set `USE_CN_MIRROR=1` before running the wrapper to set
`HF_ENDPOINT=https://hf-mirror.com` when `HF_ENDPOINT` is not already set:

```powershell
$env:USE_CN_MIRROR = "1"
.\scripts\cli\tagger.ps1 local --path .\input
```

```bash
USE_CN_MIRROR=1 bash scripts/cli/tagger.sh local --path ./input
```

Mirror note: the code path honors `HF_ENDPOINT`, but the mirror itself must be
compatible with the installed `huggingface_hub` version and the target model's
large-file hosting. If mirror metadata resolution fails, unset `HF_ENDPOINT` or
prefetch the model into `huggingface/` by another network path.

Local model priority:

1. If `MIKAZUKI_TAGGER_DIR` is set, the loader checks that directory first.
2. Then it checks project-local built-in locations:
   - `taggers/<model-key>/`
   - `models/taggers/<model-key>/`
   - `huggingface/taggers/<model-key>/`
3. If required files are present, they are used directly and no network download
   is attempted.
4. If no local files are found, Hugging Face download is attempted through
   `HF_ENDPOINT`, `--hf-endpoint`, `--use-cn-mirror`, or direct HF in that order.

For WD taggers, place `model.onnx` and `selected_tags.csv` together, for example:

```text
taggers/
  wd14-convnextv2-v2/
    model.onnx
    selected_tags.csv
```

For `cl_tagger_1_01`, place `model.onnx` and `tag_mapping.json` together:

```text
taggers/
  cl_tagger_1_01/
    model.onnx
    tag_mapping.json
```

### Local NL caption mode

Caption mode uses a local Hugging Face BLIP-compatible caption model and writes
natural-language captions beside each image:

```powershell
python -m mikazuki.tagger.cli caption --path .\input
```

```bash
python -m mikazuki.tagger.cli caption --path ./input
```

Defaults:

- Model: `Salesforce/blip-image-captioning-base`
- Output: natural-language `.txt` captions
- Cache: project `huggingface/` folder unless `HF_HOME` is already set

Useful options:

- `--model Salesforce/blip-image-captioning-base`: Hugging Face model id.
- `--prompt "a photo of"`: optional conditional caption prompt.
- `--device auto|cpu|cuda`: torch device selection.
- `--max-new-tokens 64`: generated caption length cap.
- `--use-cn-mirror` / `--hf-endpoint`: download source for missing caption
  model files.
- `--recursive`, `--additional-tags`, `--exclude-tags`, and `--on-conflict`
  behave like API NL mode.

First-run model downloads print a stage message and then rely on Hugging Face /
Transformers console progress for file downloads. This satisfies the command-line
progress requirement; WebUI SSE/WebSocket progress remains a later UI task.

### API NL mode

API mode calls an OpenAI-compatible Chat Completions vision endpoint and writes a
natural-language caption beside each image:

```powershell
$env:OPENAI_API_KEY = "sk-..."
python -m mikazuki.tagger.cli api --path .\input --model gpt-4o-mini `
  --prompt "Describe this image for LoRA training. Return one concise caption."
```

```bash
export OPENAI_API_KEY="sk-..."
python -m mikazuki.tagger.cli api --path ./input --model gpt-4o-mini \
  --prompt "Describe this image for LoRA training. Return one concise caption."
```

Useful options:

- `--endpoint https://api.openai.com/v1`: base endpoint. The CLI posts to
  `{endpoint}/chat/completions`.
- `--api-key sk-...`: explicit key. This takes precedence over env lookup.
- `--api-key-env OPENAI_API_KEY`: environment variable used when `--api-key` is
  not provided.
- `--timeout 60`: request timeout per image.
- `--retries 2`: retry count per image.
- `--recursive`, `--additional-tags`, `--exclude-tags`, and `--on-conflict`
  behave like local mode. For API captions, additional/exclude values are applied
  as comma/newline text fragments rather than confidence-scored tags.

API mode sends image bytes to the configured endpoint. Users should confirm
privacy, safety, and billing terms for their provider before running it on a
dataset.

## Output Rules

- Supported images are detected through Pillow's registered image extensions.
- A sidecar caption is written as `image_name.txt` in the same directory as the
  image.
- `local` writes Danbooru-style TAG captions; `caption` and `api` write
  natural-language captions.
- `--on-conflict ignore` skips images that already have a sidecar `.txt`.
- `--on-conflict copy` replaces existing text.
- `--on-conflict prepend` writes the new caption before the existing text.
- Duplicate comma-separated fragments are removed while preserving first
  occurrence order.

## OpenAI-Compatible Request Shape

The CLI sends a `POST` request to `{endpoint}/chat/completions`:

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Describe this image for image model training."
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,..."
          }
        }
      ]
    }
  ]
}
```

The response parser expects:

```json
{
  "choices": [
    {
      "message": {
        "content": "A natural-language caption."
      }
    }
  ]
}
```

If the response does not contain `choices[0].message.content`, the CLI fails with
a clear error and does not silently write an empty caption.

## Interface Reference

Public command-line interfaces:

- `python -m mikazuki.tagger.cli local`: local TAG tagging with WD/CL ONNX
  interrogators.
- `python -m mikazuki.tagger.cli caption`: local NL captioning with a
  BLIP-compatible Hugging Face model.
- `python -m mikazuki.tagger.cli api`: OpenAI-compatible NL captioning through
  Chat Completions vision.
- `scripts/cli/tagger.ps1` and `scripts/cli/tagger.sh`: thin wrappers that set
  project-local cache defaults and forward arguments.

Programmatic interfaces reserved for WebUI or future tooling reuse:

- `run_local_tagger(...)`: local TAG batch runner.
- `run_caption_tagger(...)`: local NL batch runner.
- `run_api_tagger(...)`: API NL batch runner.
- `OpenAICompatibleCaptionClient`: API client using `/chat/completions`.
- `LocalBlipCaptionClient`: local BLIP-compatible caption client.
- Existing WebUI endpoint `POST /interrogate`: still accepts the current
  `TaggerInterrogateRequest` fields and now delegates to `run_local_tagger`.

No dataset tag editor API is introduced in this phase.

## Later Model Candidate

PixAI Tagger v0.9 is a strong future local TAG candidate because its model card
describes a newer Danbooru snapshot through 2025-01 and about 13.5k
Danbooru-style tags. It is intentionally not added in this first CLI pass because
it would introduce new dependency and model-size decisions beyond the existing
WD/CL ONNX path.
