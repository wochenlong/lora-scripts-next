"""Background jobs for tagger prefetch and batch interrogate."""

from __future__ import annotations

from mikazuki.tagger.interrogator import available_interrogators, on_interrogate
from mikazuki.tagger.model_fetch import (
    download_interrogator_assets,
    ensure_interrogator_assets,
    interrogator_assets_ready,
    use_download_endpoint,
)
from mikazuki.tagger.progress import TaggerCancelled, tagger_progress


def run_prefetch_job(req) -> None:
    model_key = req.interrogator_model
    interrogator = available_interrogators.get(model_key)
    if interrogator is None:
        tagger_progress.finish_error(f"未知模型: {model_key}")
        return

    if not tagger_progress.try_begin("downloading", model_key, "正在准备下载…"):
        return

    try:
        with use_download_endpoint(getattr(req, "download_endpoint", "")):
            if interrogator_assets_ready(interrogator, model_key):
                tagger_progress.finish_download_success(f"模型 {model_key} 已在本地")
                return
            download_interrogator_assets(model_key, interrogator, continue_to_tagging=False)
    except TaggerCancelled:
        tagger_progress.finish_cancelled()
    except Exception as exc:  # noqa: BLE001 — surface to WebUI
        if tagger_progress.is_cancel_requested():
            tagger_progress.finish_cancelled()
        else:
            tagger_progress.finish_error(str(exc))


def run_interrogate_job(req) -> None:
    model_key = req.interrogator_model
    interrogator = available_interrogators.get(
        model_key, available_interrogators["wd14-convnextv2-v2"]
    )

    needs_download = not interrogator_assets_ready(interrogator, model_key)
    initial_phase = "downloading" if needs_download else "tagging"
    initial_message = (
        "正在下载模型，完成后自动开始打标…"
        if needs_download
        else "正在准备打标…"
    )

    if not tagger_progress.try_begin(initial_phase, model_key, initial_message):
        return

    try:
        with use_download_endpoint(getattr(req, "download_endpoint", "")):
            if needs_download:
                ensure_interrogator_assets(model_key, interrogator)

        tagger_progress.check_cancelled()

        result = on_interrogate(
            image=None,
            batch_input_glob=req.path,
            batch_input_recursive=req.batch_input_recursive,
            batch_output_dir="",
            batch_output_filename_format="[name].[output_extension]",
            batch_output_action_on_conflict=req.batch_output_action_on_conflict,
            batch_remove_duplicated_tag=True,
            batch_output_save_json=False,
            interrogator=interrogator,
            threshold=req.threshold,
            character_threshold=req.character_threshold,
            add_rating_tag=req.add_rating_tag,
            add_model_tag=req.add_model_tag,
            additional_tags=req.additional_tags,
            exclude_tags=req.exclude_tags,
            sort_by_alphabetical_order=False,
            add_confident_as_weight=False,
            replace_underscore=req.replace_underscore,
            replace_underscore_excludes=req.replace_underscore_excludes,
            escape_tag=req.escape_tag,
            unload_model_after_running=True,
            progress_model_key=model_key,
        )
        if result == "Succeed":
            tagger_progress.finish_success("打标完成")
        elif result == "Cancelled":
            tagger_progress.finish_cancelled()
        else:
            tagger_progress.finish_error(result or "打标失败")
    except TaggerCancelled:
        tagger_progress.finish_cancelled()
    except Exception as exc:  # noqa: BLE001
        if tagger_progress.is_cancel_requested():
            tagger_progress.finish_cancelled()
        else:
            tagger_progress.finish_error(str(exc))
