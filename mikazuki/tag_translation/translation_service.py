# This file is adapted from ComfyUI-Autocomplete-Aaalice.
# Source snapshot: 37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0
# License: MIT; see docs/third_party/comfyui-autocomplete-aaalice-MIT.txt.
# Next Trainer changes are tracked in git history.

import asyncio
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

from .translation_config import OnlineServiceConfig, local_llm_endpoint, local_proxy_endpoint, mask_config
from .translation_store import is_translation_acceptable
from mikazuki.llm.http import LLMRequestError, post_chat
from mikazuki.llm.contracts import LLMContractError


DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODELS_URL = "https://api.deepseek.com/models"
USER_AGENT = "Autocomplete-Plus/1.12"
SUPPORTED_LOCALES = {
    "zh": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "ja": "Japanese",
    "en": "English",
}
MAX_TRANSLATION_ITEMS_PER_REQUEST = 25_000


class TranslationError(RuntimeError):
    def __init__(self, message, code="translation_error"):
        super().__init__(message)
        self.code = code


class RetryableTranslationError(TranslationError):
    def __init__(self, message, retry_after=None):
        super().__init__(message, "deepseek_request_failed")
        self.retry_after = retry_after


@dataclass
class TranslationResult:
    translations: dict
    failures: list


class DynamicConcurrencyLimiter:
    """Shares one adjustable DeepSeek concurrency budget across all requests."""

    def __init__(self):
        self._active = 0
        self._limit = 1
        self._condition = asyncio.Condition()

    async def run(self, limit, operation):
        async with self._condition:
            self._limit = max(int(limit), 1)
            while self._active >= self._limit:
                await self._condition.wait()
            self._active += 1
        try:
            return await operation()
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify_all()


class DeepSeekClient:
    def __init__(self, session, config):
        self.session = session
        self.config = config

    async def translate(self, items, locale):
        translations, failures = await self._translate_items(items, locale, self.config["max_retries"])
        return TranslationResult(translations, failures)

    async def _translate_items(self, items, locale, retries_left):
        if not items:
            return {}, []
        try:
            response_payload = await self._request(items, locale)
        except (RetryableTranslationError, aiohttp.ClientError, asyncio.TimeoutError) as error:
            if retries_left <= 0:
                return {}, [item["name"] for item in items]
            await self._retry_delay(self.config["max_retries"] - retries_left, getattr(error, "retry_after", None))
            return await self._translate_items(items, locale, retries_left - 1)

        if response_payload.get("finish_reason") == "length" and len(items) > 1:
            midpoint = math.ceil(len(items) / 2)
            left, right = await asyncio.gather(
                self._translate_items(items[:midpoint], locale, retries_left),
                self._translate_items(items[midpoint:], locale, retries_left),
            )
            return {**left[0], **right[0]}, left[1] + right[1]

        valid, missing = validate_translation_response(response_payload.get("content"), items, locale)
        if not missing or retries_left <= 0:
            return valid, missing
        missing_set = set(missing)
        missing_items = [item for item in items if item["name"] in missing_set]
        await self._retry_delay(self.config["max_retries"] - retries_left)
        retried, failures = await self._translate_items(missing_items, locale, retries_left - 1)
        valid.update(retried)
        return valid, failures

    async def _request(self, items, locale):
        schema_instruction = (
            "Return valid JSON only, using exactly this schema: "
            '{"translations":[{"tag":"original_tag","translation":"translated text"}]}. '
            "Return every input tag exactly once and do not add unknown tags. "
            "Every translation must use the target language writing system and must not repeat the original tag."
        )
        payload = {
            "model": self.config["model"],
            "messages": [
                {"role": "system", "content": f"{self.config['system_prompt']}\n\n{schema_instruction}"},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "target_language": SUPPORTED_LOCALES[locale],
                            "tags": [{"tag": item["name"], "category": item["category"]} for item in items],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }
        if local_llm_endpoint(self.config.get("endpoint")):
            payload["thinking"] = {"type": "disabled"}
        try:
            try:
                envelope, content = await post_chat(
                    self.session,
                    self.config.get("endpoint") or DEEPSEEK_CHAT_URL,
                    payload,
                    self.config.get("api_key", ""),
                    extra_headers={"User-Agent": USER_AGENT},
                )
            except (LLMRequestError, aiohttp.ClientError, asyncio.TimeoutError):
                fallbacks = self.config.get("_fallbacks") or []
                if not fallbacks:
                    raise
                fallback = fallbacks[0]
                envelope, content = await post_chat(
                    self.session, fallback["endpoint"],
                    {**payload, "model": fallback["model"]},
                    fallback.get("api_key", ""),
                    extra_headers={"User-Agent": USER_AGENT},
                )
            return {"content": content, "finish_reason": envelope["choices"][0].get("finish_reason")}
        except LLMRequestError as error:
            if error.retryable:
                raise RetryableTranslationError(str(error)) from error
            raise TranslationError(str(error), error.code) from error
        except LLMContractError as error:
            raise TranslationError("LLM returned an invalid response envelope", "llm_invalid_response") from error

    async def _retry_delay(self, attempt, retry_after=None):
        try:
            delay = float(retry_after) if retry_after is not None else 2**attempt + random.random()
        except ValueError:
            delay = 2**attempt + random.random()
        await asyncio.sleep(min(max(delay, 0), 60))


class TranslationManager:
    def __init__(self, config_path, store, session_factory=None, config_store=None, primary_store=None):
        self.config_store = config_store or OnlineServiceConfig(config_path)
        self.store = store
        self.primary_store = primary_store
        self.session_factory = session_factory or aiohttp.ClientSession
        self._inflight = {}
        self._inflight_lock = asyncio.Lock()
        self._workers = set()
        self._translation_limiter = DynamicConcurrencyLimiter()
        self._last_status = {"state": "idle", "message": "", "updated_at": None}

    def get_config(self):
        config = self.config_store.load()
        if isinstance(config.get("llm"), dict):
            from mikazuki.llm.config import UnifiedConfigStore
            from mikazuki.llm.service import UnifiedLLMService
            config["llm"] = UnifiedLLMService(UnifiedConfigStore(self.config_store.path)).config(masked=True)
        return mask_config(config)

    def get_api_key(self):
        return self.config_store.load()["deepseek"]["api_key"]

    def cache_enabled(self):
        return self.config_store.load().get("llm", {}).get("cache", {}).get("translation", True)

    def _active_llm_config(self, full_config):
        section = full_config["deepseek"].copy()
        shared = full_config.get("llm")
        if isinstance(shared, dict):
            from mikazuki.llm.config import UnifiedConfigStore
            from mikazuki.llm.service import UnifiedLLMService
            shared = UnifiedLLMService(UnifiedConfigStore(self.config_store.path)).config(masked=False)
        section["_cache_enabled"] = not isinstance(shared, dict) or shared.get("cache", {}).get("translation", True)
        if isinstance(shared, dict) and shared.get("profiles"):
            from mikazuki.llm.routing import choose_profile
            profile = choose_profile(
                shared["profiles"], "text",
                preferred_id=shared.get("routes", {}).get("translation"),
                allow_local_fallback=bool(full_config.get("local", {}).get("enabled")),
            )
            legacy = next((item for item in full_config.get("remote_profiles", []) if item["id"] == profile.id), {})
            section.update({key: value for key, value in legacy.items() if key in {"system_prompt", "reasoning_effort"}})
            section.update(endpoint=profile.endpoint, model=profile.model, api_key=profile.api_key)
            section["secret_revision"] = profile.metadata.get("secret_revision", 0)
            section["_fallbacks"] = [
                candidate for candidate in shared["profiles"]
                if full_config.get("local", {}).get("enabled")
                and profile.is_remote and candidate.get("source") != "remote"
                and candidate.get("enabled") and candidate.get("ready")
                and "text" in candidate.get("capabilities", [])
            ]
        native_ready = False
        if full_config.get("local", {}).get("enabled"):
            from mikazuki.llm.runtime import llm_config_store
            if self.config_store.path == llm_config_store.path:
                from mikazuki.tag_translation.runtime import local_model_service
                native_ready = local_model_service.status()["state"] == "running"
        if native_ready and section.get("api_key") and not any(profile.get("asset_id") == "qwen3.5-0.8b-local" for profile in section.get("_fallbacks", [])):
            section.setdefault("_fallbacks", []).append({
                "endpoint": local_proxy_endpoint(), "model": "qwen3.5-0.8b-q4_0", "api_key": "",
            })
        elif full_config.get("local", {}).get("enabled") and not section.get("api_key") and not shared:
            section["endpoint"] = local_proxy_endpoint()
        return section

    def profile_revision(self, config=None):
        if config is None:
            full_config = self.config_store.load()
            section = self._active_llm_config(full_config)
        else:
            section = config
        payload = {
            "endpoint": section.get("endpoint", ""),
            "model": section.get("model", ""),
            "system_prompt": section.get("system_prompt", ""),
            "reasoning_effort": section.get("reasoning_effort", "disabled"),
            "secret_revision": section.get("secret_revision", 0),
            "fallback_revisions": [
                {key: profile.get(key) for key in ("endpoint", "model", "revision", "secret_revision")}
                for profile in section.get("_fallbacks", [])
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]

    def save_config(self, raw_config):
        return mask_config(self.config_store.save(raw_config))

    def status(self):
        full_config = self.config_store.load()
        config = full_config["deepseek"]
        local_config = full_config.get("local", {})
        return {
            "cache_count": self.store.result_count("llm"),
            "deepseek": self._last_status.copy(),
            "configured": bool(
                config["api_key"]
                or local_llm_endpoint(config.get("endpoint"))
                or local_config.get("enabled")
            ),
            "local_enabled": bool(local_config.get("enabled")),
            "local_endpoint": local_config.get("endpoint", ""),
        }

    def catalog(self, locale):
        normalized_locale = normalize_locale(locale)
        catalog = self.store.catalog(normalized_locale)
        if normalized_locale in {"zh", "zh-TW"} and self.primary_store is not None and catalog:
            primary = self._lookup_primary([row["tag_name"] for row in catalog])
            return [
                {**row, **primary.get(row["tag_name"], {})}
                for row in catalog
            ]
        return catalog

    async def list_models(self, supplied_key=None):
        config = self.config_store.load()["deepseek"]
        api_key = self._resolve_api_key(supplied_key, config["api_key"])
        if not api_key:
            raise TranslationError("Configure a DeepSeek API key first", "deepseek_key_missing")
        timeout = aiohttp.ClientTimeout(total=min(config["timeout_seconds"], 30))
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "User-Agent": USER_AGENT}
        try:
            async with self.session_factory(timeout=timeout) as session:
                async with session.get(DEEPSEEK_MODELS_URL, headers=headers) as response:
                    body = await response.text()
                    if response.status == 401:
                        raise TranslationError("DeepSeek rejected the API key", "deepseek_auth_failed")
                    if response.status != 200:
                        raise TranslationError(f"DeepSeek returned HTTP {response.status}", "deepseek_request_failed")
            payload = json.loads(body)
            models = sorted({str(item.get("id")) for item in payload.get("data", []) if item.get("id")})
            self._set_status("success", f"Loaded {len(models)} model(s)")
            return models
        except Exception as error:
            self._set_status("error", str(error)[:500])
            raise

    async def test_model(self, supplied_key, model, reasoning_effort="disabled"):
        config = self.config_store.load()["deepseek"].copy()
        config["api_key"] = self._resolve_api_key(supplied_key, config["api_key"])
        config["model"] = str(model or config["model"]).strip()
        config["reasoning_effort"] = reasoning_effort if reasoning_effort in {"disabled", "high", "max"} else "disabled"
        if not config["api_key"]:
            raise TranslationError("Configure a DeepSeek API key first", "deepseek_key_missing")
        timeout = aiohttp.ClientTimeout(total=min(config["timeout_seconds"], 30))
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": "Reply with OK only."}],
            "thinking": {"type": "disabled" if config["reasoning_effort"] == "disabled" else "enabled"},
            "max_tokens": 8,
        }
        if config["reasoning_effort"] != "disabled":
            payload["reasoning_effort"] = config["reasoning_effort"]
        try:
            async with self.session_factory(timeout=timeout) as session:
                async with session.post(DEEPSEEK_CHAT_URL, json=payload, headers=headers) as response:
                    body = await response.text()
                    if response.status == 401:
                        raise TranslationError("DeepSeek rejected the API key", "deepseek_auth_failed")
                    if response.status != 200:
                        raise TranslationError(f"DeepSeek returned HTTP {response.status}", "deepseek_request_failed")
            result = json.loads(body)
            result["choices"][0]["message"]
            self._set_status("success", f"Model {config['model']} is available")
            return {"ok": True, "model": config["model"]}
        except Exception as error:
            self._set_status("error", str(error)[:500])
            raise

    async def resolve(self, locale, raw_items, refresh=False):
        live = {}
        async for chunk in self.resolve_stream(locale, raw_items, refresh=refresh):
            for tag, text in chunk["translations"].items():
                live[tag] = {"text": text, "origin": chunk["sources"].get(tag, "deepseek")}
        locale = normalize_locale(locale)
        tag_names = [item["name"] for item in normalize_items(raw_items)]
        full_config = self.config_store.load()
        active_config = self._active_llm_config(full_config)
        if not active_config["_cache_enabled"]:
            return live
        profile_revision = self.profile_revision(active_config)
        cached = await asyncio.to_thread(
            self.store.get_results, locale, tag_names, "llm", profile_revision
        )
        primary = await self._get_primary(locale, tag_names)
        return {**cached, **primary}

    async def resolve_stream(self, locale, raw_items, refresh=False):
        locale = normalize_locale(locale)
        normalized_items = normalize_items(raw_items)
        full_config = self.config_store.load()
        config = self._active_llm_config(full_config)
        cache_enabled = config["_cache_enabled"]
        local_config = full_config.get("local", {})
        profile_revision = self.profile_revision(config)
        if not cache_enabled:
            profile_revision += ":no-cache"
        primary = await self._get_primary(locale, [item["name"] for item in normalized_items])
        primary_translations = {
            tag_name: row["text"] for tag_name, row in primary.items() if row.get("text")
        }
        if primary_translations:
            yield {
                "translations": primary_translations,
                "sources": dict.fromkeys(primary_translations, "ffdkj"),
                "completed": list(primary_translations),
            }
        items = [
            item for item in normalized_items
            if item["category"] != 1 and item["name"] not in primary
        ]
        tag_names = [item["name"] for item in items]
        cached = {} if refresh or not cache_enabled else await asyncio.to_thread(
            self.store.get_results, locale, tag_names, "llm", profile_revision
        )
        cached_translations = {
            tag_name: row["text"] for tag_name, row in cached.items() if row.get("text")
        }
        if cached_translations:
            yield {
                "translations": cached_translations,
                "sources": dict.fromkeys(cached_translations, "ai_cache"),
                "completed": list(cached_translations),
            }
        if locale == "en" or not items:
            return
        if (
            locale in {"zh", "zh-TW"}
            and self.primary_store is not None
            and self.primary_store.status().get("state") in {"missing", "checking", "downloading"}
        ):
            return

        if not full_config["features"]["translation"]:
            return
        missing = [item for item in items if item["name"] not in cached]
        # Tags without letters (aspect ratios, kaomoji) are untranslatable;
        # asking DeepSeek only burns retries while the client spinner waits.
        skipped = [item["name"] for item in missing if not has_translatable_characters(item["name"])]
        if skipped:
            yield {"translations": {}, "sources": {}, "completed": skipped}
        missing = [item for item in missing if has_translatable_characters(item["name"])]
        # Tags that already exhausted retries with this model and prompt are
        # treated as resolved-without-translation instead of being re-asked.
        prompt_hash = hashlib.sha256(config["system_prompt"].encode("utf-8")).hexdigest()
        known_failures = set() if refresh or not cache_enabled else await asyncio.to_thread(
            self.store.get_failures,
            locale,
            [item["name"] for item in missing],
            config["model"],
            prompt_hash,
        )
        if known_failures:
            yield {"translations": {}, "sources": {}, "completed": sorted(known_failures)}
            missing = [item for item in missing if item["name"] not in known_failures]
        if not (config["api_key"] or local_llm_endpoint(config.get("endpoint"))) or not missing:
            return

        owned = []
        futures = {}
        refreshed_translations = {}
        loop = asyncio.get_running_loop()
        async with self._inflight_lock:
            # Another request can finish between the first SQLite lookup and
            # acquiring this lock. Refresh here so a just-persisted translation
            # is not purchased again after its in-flight entry was removed.
            refreshed = {} if refresh or not cache_enabled else await asyncio.to_thread(
                self.store.get_results,
                locale,
                [item["name"] for item in missing],
                "llm",
                profile_revision,
            )
            cached.update(refreshed)
            refreshed_translations = {
                tag_name: row["text"]
                for tag_name, row in refreshed.items()
                if tag_name not in cached_translations and row.get("text")
            }
            for item in missing:
                if item["name"] in cached:
                    continue
                key = (locale, profile_revision, item["name"])
                future = self._inflight.get(key)
                if future is None:
                    future = loop.create_future()
                    self._inflight[key] = future
                    owned.append(item)
                futures[item["name"]] = future

        if refreshed_translations:
            yield {
                "translations": refreshed_translations,
                "sources": dict.fromkeys(refreshed_translations, "ai_cache"),
                "completed": list(refreshed_translations),
            }

        if owned:
            worker = asyncio.create_task(self._translate_owned(locale, profile_revision, owned, config))
            self._workers.add(worker)
            worker.add_done_callback(self._workers.discard)

        async def wait_for_tag(tag_name, future):
            return tag_name, await asyncio.shield(future)

        waiters = [
            asyncio.create_task(wait_for_tag(tag_name, future))
            for tag_name, future in futures.items()
        ]
        pending_waiters = set(waiters)
        try:
            while pending_waiters:
                completed, pending_waiters = await asyncio.wait(
                    pending_waiters,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                chunk = {}
                completed_tags = []
                for waiter in completed:
                    tag_name, translation = waiter.result()
                    completed_tags.append(tag_name)
                    if translation:
                        chunk[tag_name] = translation
                yield {
                    "translations": chunk,
                    "sources": dict.fromkeys(chunk, "deepseek"),
                    "completed": completed_tags,
                }
        finally:
            for waiter in pending_waiters:
                if not waiter.done():
                    waiter.cancel()

    async def _get_primary(self, locale, tag_names):
        if locale not in {"zh", "zh-TW"} or self.primary_store is None or not tag_names:
            return {}
        return await asyncio.to_thread(self._lookup_primary, tag_names)

    def _lookup_primary(self, tag_names):
        lookup = getattr(self.primary_store, "lookup_all", self.primary_store.lookup)
        return lookup(tag_names)

    async def _translate_owned(self, locale, profile_revision, items, config):
        translations = {}
        errors = []
        try:
            timeout = aiohttp.ClientTimeout(total=config["timeout_seconds"])
            connector = aiohttp.TCPConnector(limit=config["concurrency"])
            async with self.session_factory(timeout=timeout, connector=connector) as session:
                client = DeepSeekClient(session, config)
                batches = [
                    items[index : index + config["batch_size"]]
                    for index in range(0, len(items), config["batch_size"])
                ]
                async def translate_batch(batch):
                    async def operation():
                        return await client.translate(batch, locale)

                    try:
                        result = await self._translation_limiter.run(config["concurrency"], operation)
                        return batch, result, None
                    except Exception as error:
                        return batch, None, error

                tasks = [asyncio.create_task(translate_batch(batch)) for batch in batches]
                for completed in asyncio.as_completed(tasks):
                    batch, result, error = await completed
                    if error is not None:
                        errors.append(error)
                        await self._finish_inflight_batch(locale, profile_revision, batch, {})
                        continue
                    translations.update(result.translations)
                    prompt_hash = hashlib.sha256(config["system_prompt"].encode("utf-8")).hexdigest()
                    if result.translations and config.get("_cache_enabled", True):
                        await asyncio.to_thread(
                            self.store.save_results,
                            locale,
                            "llm",
                            self.profile_revision(config),
                            batch,
                            result.translations,
                        )
                    if result.failures and config.get("_cache_enabled", True):
                        await asyncio.to_thread(
                            self.store.save_failures,
                            locale,
                            batch,
                            result.failures,
                            config["model"],
                            prompt_hash,
                        )
                    await self._finish_inflight_batch(locale, profile_revision, batch, result.translations)
            if errors:
                self._set_status("error", str(errors[0])[:500])
            else:
                self._set_status("success", f"Translated {len(translations)} tag(s)")
        except Exception as caught:
            self._set_status("error", str(caught)[:500])
        finally:
            await self._finish_inflight_batch(locale, profile_revision, items, translations)

    async def _finish_inflight_batch(self, locale, profile_revision, items, translations):
        async with self._inflight_lock:
            for item in items:
                key = (locale, profile_revision, item["name"])
                future = self._inflight.pop(key, None)
                if future is not None and not future.done():
                    future.set_result(translations.get(item["name"]))

    def _set_status(self, state, message):
        self._last_status = {
            "state": state,
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _resolve_api_key(supplied_key, saved_key):
        value = str(supplied_key or "").strip()
        return saved_key if value in {"", "********"} else value


def normalize_locale(locale):
    normalized = str(locale or "en").replace("_", "-")
    lowered = normalized.lower()
    locale_parts = lowered.split("-")
    if lowered.startswith("zh") and (
        "hant" in locale_parts
        or "cht" in locale_parts
        or any(part in {"tw", "hk", "mo"} for part in locale_parts)
    ):
        return "zh-TW"
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("ja"):
        return "ja"
    return "en"


def has_translatable_characters(name):
    return any(character.isalpha() for character in name)


def normalize_items(raw_items):
    if not isinstance(raw_items, list):
        raise ValueError("tags must be an array")
    normalized = []
    seen = set()
    for raw_item in raw_items[:MAX_TRANSLATION_ITEMS_PER_REQUEST]:
        if not isinstance(raw_item, dict):
            continue
        name = str(raw_item.get("name") or "").strip()
        if not name or len(name) > 200 or name in seen:
            continue
        seen.add(name)
        try:
            category = int(raw_item.get("category") or 0)
            post_count = max(int(raw_item.get("post_count") or 0), 0)
        except (TypeError, ValueError):
            continue
        origin = "danbooru_api" if raw_item.get("origin") == "danbooru_api" else "local"
        normalized.append(
            {"name": name, "category": category, "post_count": post_count, "origin": origin}
        )
    return normalized


def validate_translation_response(content, items, locale):
    expected = {item["name"] for item in items}
    categories = {item["name"]: item["category"] for item in items}
    if not isinstance(content, str) or not content.strip():
        return {}, sorted(expected)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}, sorted(expected)
    entries = payload.get("translations") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {}, sorted(expected)

    valid = {}
    invalid = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tag = entry.get("tag")
        translation = entry.get("translation")
        if tag not in expected:
            return {}, sorted(expected)
        invalid_translation = (
            not isinstance(translation, str)
            or not translation.strip()
            or any(character in translation for character in ("\r", "\n", "\x00"))
            or not is_translation_acceptable(
                tag,
                translation,
                locale,
                categories[tag],
            )
        )
        if tag in valid or invalid_translation:
            if tag in expected:
                invalid.add(tag)
            continue
        valid[tag] = translation.strip()
    for tag in invalid:
        valid.pop(tag, None)
    return valid, sorted(expected - valid.keys())
