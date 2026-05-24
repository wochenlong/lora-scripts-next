from __future__ import annotations

import base64
import copy
import mimetypes
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Iterable, Protocol

import httpx
from PIL import Image, UnidentifiedImageError

from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.interrogators.base import Interrogator


DEFAULT_OPENAI_ENDPOINT = "https://api.openai.com/v1"
DEFAULT_API_PROMPT = (
    "Describe this image for image model training. Return a concise natural-language "
    "caption only, without markdown or explanations."
)
DEFAULT_LOCAL_CAPTION_MODEL = "Salesforce/blip-image-captioning-base"
REPO_ROOT = Path(__file__).resolve().parents[2]


def ensure_project_hf_home() -> Path:
    hf_home = Path(os.environ.get("HF_HOME", REPO_ROOT / "huggingface")).resolve()
    os.environ["HF_HOME"] = str(hf_home)
    hf_home.mkdir(parents=True, exist_ok=True)
    return hf_home


def configure_hf_download(
    *,
    use_cn_mirror: bool = False,
    hf_endpoint: str | None = None,
) -> Path:
    hf_home = ensure_project_hf_home()
    if hf_endpoint:
        os.environ["HF_ENDPOINT"] = hf_endpoint
    elif use_cn_mirror and not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    return hf_home


@dataclass
class TaggerRunResult:
    found: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0


class CaptionClient(Protocol):
    def caption(self, image_path: Path) -> str:
        ...


def split_csv(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = value
    return [str(part).strip() for part in parts if str(part).strip()]


def collect_image_paths(input_path: str, recursive: bool = False) -> list[Path]:
    path_text = input_path.strip()
    if not path_text:
        return []

    Image.init()
    supported_extensions = {
        ext.lower()
        for ext, opener in Image.registered_extensions().items()
        if opener in Image.OPEN
    }

    candidate_paths: list[Path]
    path = Path(path_text)
    if any(mark in path_text for mark in ("*", "?")):
        candidate_paths = [Path(item) for item in glob(path_text, recursive=recursive)]
    elif path.is_dir():
        pattern = "**/*" if recursive else "*"
        candidate_paths = [item for item in path.glob(pattern)]
    elif path.is_file():
        candidate_paths = [path]
    else:
        raise ValueError(f"input path does not exist: {input_path}")

    return sorted(
        item
        for item in candidate_paths
        if item.is_file() and item.suffix.lower() in supported_extensions
    )


def merge_output(
    existing_text: str,
    new_text: str,
    *,
    on_conflict: str,
    remove_duplicated_tag: bool = True,
) -> str:
    if not existing_text:
        merged = new_text
    elif on_conflict == "copy":
        merged = new_text
    elif on_conflict == "prepend":
        merged = f"{new_text}, {existing_text}"
    else:
        merged = f"{existing_text}, {new_text}"

    if not remove_duplicated_tag:
        return merged.strip()

    return ", ".join(
        OrderedDict.fromkeys(part.strip() for part in merged.split(",") if part.strip())
    )


def apply_text_fragments(text: str, additional_tags: str = "", exclude_tags: str = "") -> str:
    additions = split_csv(additional_tags)
    excludes = set(split_csv(exclude_tags))
    fragments = [
        fragment.strip()
        for line in text.splitlines()
        for fragment in line.split(",")
        if fragment.strip()
    ]
    fragments = [fragment for fragment in fragments if fragment not in excludes]
    fragments.extend(addition for addition in additions if addition not in excludes)
    return ", ".join(OrderedDict.fromkeys(fragments))


def write_caption(
    image_path: Path,
    caption: str,
    *,
    on_conflict: str,
    remove_duplicated_tag: bool = True,
) -> bool:
    output_path = image_path.with_suffix(".txt")
    if output_path.is_file():
        existing_text = output_path.read_text(encoding="utf-8", errors="ignore").strip()
        if on_conflict == "ignore":
            return False
    else:
        existing_text = ""

    output_path.write_text(
        merge_output(
            existing_text,
            caption,
            on_conflict=on_conflict,
            remove_duplicated_tag=remove_duplicated_tag,
        ),
        encoding="utf-8",
    )
    return True


def run_local_tagger(
    input_path: str,
    *,
    model: str = "wd14-convnextv2-v2",
    threshold: float = 0.35,
    character_threshold: float = 0.6,
    recursive: bool = False,
    additional_tags: str = "",
    exclude_tags: str = "",
    on_conflict: str = "ignore",
    replace_underscore: bool = True,
    replace_underscore_excludes: str = "",
    escape_tag: bool = True,
    add_rating_tag: bool = False,
    add_model_tag: bool = False,
    unload_model_after_running: bool = True,
    use_cn_mirror: bool = False,
    hf_endpoint: str | None = None,
) -> TaggerRunResult:
    configure_hf_download(use_cn_mirror=use_cn_mirror, hf_endpoint=hf_endpoint)
    image_paths = collect_image_paths(input_path, recursive=recursive)
    result = TaggerRunResult(found=len(image_paths))
    interrogator = available_interrogators.get(model, available_interrogators["wd14-convnextv2-v2"])

    try:
        for image_path in image_paths:
            if image_path.with_suffix(".txt").is_file() and on_conflict == "ignore":
                result.skipped += 1
                print(f"skipping {image_path}")
                continue

            try:
                with Image.open(image_path) as image:
                    tags = interrogator.interrogate(image)
            except UnidentifiedImageError:
                result.failed += 1
                print(f"{image_path} is not supported image type")
                continue
            except Exception:
                result.failed += 1
                raise

            processed_tags = Interrogator.postprocess_tags(
                copy.deepcopy(tags),
                threshold,
                character_threshold,
                add_rating_tag,
                add_model_tag,
                split_csv(additional_tags),
                split_csv(exclude_tags),
                False,
                False,
                replace_underscore,
                split_csv(replace_underscore_excludes),
                escape_tag,
            )
            caption = ", ".join(processed_tags)
            if write_caption(image_path, caption, on_conflict=on_conflict):
                result.processed += 1
                print(f"tagged {image_path} ({len(processed_tags)} tags)")
            else:
                result.skipped += 1
                print(f"skipping {image_path}")
    finally:
        if unload_model_after_running:
            interrogator.unload()

    return result


class OpenAICompatibleCaptionClient:
    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_OPENAI_ENDPOINT,
        api_key: str,
        model: str,
        prompt: str = DEFAULT_API_PROMPT,
        timeout: float = 60,
        retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.url = build_chat_completions_url(endpoint)
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.timeout = timeout
        self.retries = retries
        self.http_client = http_client

    def caption(self, image_path: Path) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_to_data_url(image_path)},
                        },
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                if self.http_client is None:
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.post(self.url, headers=headers, json=payload)
                else:
                    response = self.http_client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return parse_openai_caption(data)
            except Exception as error:
                last_error = error
                if attempt >= self.retries:
                    break
                time.sleep(min(2 ** attempt, 5))

        raise RuntimeError(f"API tagging failed for {image_path}: {last_error}") from last_error


class LocalBlipCaptionClient:
    def __init__(
        self,
        *,
        model: str = DEFAULT_LOCAL_CAPTION_MODEL,
        prompt: str = "",
        device: str = "auto",
        max_new_tokens: int = 64,
        use_cn_mirror: bool = False,
        hf_endpoint: str | None = None,
    ) -> None:
        self.model_name = model
        self.prompt = prompt
        self.device_name = device
        self.max_new_tokens = max_new_tokens
        self.use_cn_mirror = use_cn_mirror
        self.hf_endpoint = hf_endpoint
        self.processor = None
        self.model = None
        self.device = None

    def load(self) -> None:
        if self.model is not None and self.processor is not None:
            return

        configure_hf_download(use_cn_mirror=self.use_cn_mirror, hf_endpoint=self.hf_endpoint)
        print(f"[tagger] Loading local caption model: {self.model_name}")
        print("[tagger] First run may download model files; Hugging Face progress is shown in the console.")

        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor

        if self.device_name == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = self.device_name

        self.processor = BlipProcessor.from_pretrained(self.model_name)
        self.model = BlipForConditionalGeneration.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()
        print(f"[tagger] Loaded {self.model_name} on {self.device}")

    def caption(self, image_path: Path) -> str:
        self.load()

        import torch
        from PIL import Image

        with Image.open(image_path) as image:
            image = image.convert("RGB")
            if self.prompt:
                inputs = self.processor(image, self.prompt, return_tensors="pt")
            else:
                inputs = self.processor(image, return_tensors="pt")

        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.no_grad():
            output = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        caption = self.processor.decode(output[0], skip_special_tokens=True).strip()

        if not caption:
            raise ValueError(f"local caption model returned an empty caption for {image_path}")
        return caption


def build_chat_completions_url(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    return f"{endpoint}/chat/completions"


def image_to_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def parse_openai_caption(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("OpenAI-compatible response does not contain choices[0].message.content") from exc

    if isinstance(content, str):
        caption = content.strip()
    elif isinstance(content, list):
        caption = " ".join(
            item.get("text", "").strip()
            for item in content
            if isinstance(item, dict) and item.get("type") in {None, "text", "output_text"}
        ).strip()
    else:
        caption = ""

    if not caption:
        raise ValueError("OpenAI-compatible response caption is empty")
    return caption


def run_api_tagger(
    input_path: str,
    *,
    client: CaptionClient,
    recursive: bool = False,
    additional_tags: str = "",
    exclude_tags: str = "",
    on_conflict: str = "ignore",
) -> TaggerRunResult:
    image_paths = collect_image_paths(input_path, recursive=recursive)
    result = TaggerRunResult(found=len(image_paths))

    for image_path in image_paths:
        output_path = image_path.with_suffix(".txt")
        if output_path.is_file() and on_conflict == "ignore":
            result.skipped += 1
            print(f"skipping {image_path}")
            continue

        try:
            caption = client.caption(image_path)
            caption = apply_text_fragments(caption, additional_tags, exclude_tags)
            write_caption(image_path, caption, on_conflict=on_conflict)
            result.processed += 1
            print(f"captioned {image_path}")
        except Exception as error:
            result.failed += 1
            print(f"failed {image_path}: {error}")
            raise

    return result


def run_caption_tagger(
    input_path: str,
    *,
    client: CaptionClient,
    recursive: bool = False,
    additional_tags: str = "",
    exclude_tags: str = "",
    on_conflict: str = "ignore",
) -> TaggerRunResult:
    return run_api_tagger(
        input_path,
        client=client,
        recursive=recursive,
        additional_tags=additional_tags,
        exclude_tags=exclude_tags,
        on_conflict=on_conflict,
    )
