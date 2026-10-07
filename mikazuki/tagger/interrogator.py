# from https://github.com/toriato/stable-diffusion-webui-wd14-tagger
import json
import os
import re
from collections import OrderedDict
from glob import glob
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image
from PIL import UnidentifiedImageError
from huggingface_hub import hf_hub_download

from mikazuki.tagger import dbimutils, format
from mikazuki.tagger.interrogators.base import Interrogator
from mikazuki.tagger.interrogators.wd14 import WaifuDiffusionInterrogator
from mikazuki.tagger.interrogators.cl import CLTaggerInterrogator
from mikazuki.tagger.progress import TaggerCancelled, tagger_progress

tag_escape_pattern = re.compile(r'([\\()])')


available_interrogators = {
    'wd-convnext-v3': WaifuDiffusionInterrogator(
        'wd-convnext-v3',
        repo_id='SmilingWolf/wd-convnext-tagger-v3',
    ),
    'wd-swinv2-v3': WaifuDiffusionInterrogator(
        'wd-swinv2-v3',
        repo_id='SmilingWolf/wd-swinv2-tagger-v3',
    ),
    'wd-vit-v3': WaifuDiffusionInterrogator(
        'wd-vit-v3',
        repo_id='SmilingWolf/wd-vit-tagger-v3',
        local_model_aliases=('wd14-vit-v3',),
    ),
    'wd14-convnextv2-v2': WaifuDiffusionInterrogator(
        'wd14-convnextv2-v2', repo_id='SmilingWolf/wd-v1-4-convnextv2-tagger-v2',
        revision='v2.0'
    ),
    'wd14-swinv2-v2': WaifuDiffusionInterrogator(
        'wd14-swinv2-v2', repo_id='SmilingWolf/wd-v1-4-swinv2-tagger-v2',
        revision='v2.0'
    ),
    'wd14-vit-v2': WaifuDiffusionInterrogator(
        'wd14-vit-v2', repo_id='SmilingWolf/wd-v1-4-vit-tagger-v2',
        revision='v2.0'
    ),
    'wd14-moat-v2': WaifuDiffusionInterrogator(
        'wd14-moat-v2',
        repo_id='SmilingWolf/wd-v1-4-moat-tagger-v2',
        revision='v2.0',
        local_model_aliases=('wd-v1-4-moat-tagger-v2',),
    ),
    'wd-eva02-large-tagger-v3': WaifuDiffusionInterrogator(
        'wd-eva02-large-tagger-v3',
        repo_id='SmilingWolf/wd-eva02-large-tagger-v3',
    ),
    'wd-vit-large-tagger-v3': WaifuDiffusionInterrogator(
        'wd-vit-large-tagger-v3',
        repo_id='SmilingWolf/wd-vit-large-tagger-v3',
    ),
    'cl_tagger_1_01': CLTaggerInterrogator(
        'cl_tagger_1_01',
        repo_id='cella110n/cl_tagger',
        model_path='cl_tagger_1_01/model.onnx',
        tag_mapping_path='cl_tagger_1_01/tag_mapping.json',
    ),
}


def split_str(s: str, separator=',') -> List[str]:
    return [x.strip() for x in s.split(separator) if x]


def on_interrogate(
        image: Image,
        batch_input_glob: str,
        batch_input_recursive: bool,
        batch_output_dir: str,
        batch_output_filename_format: str,
        batch_output_action_on_conflict: str,
        batch_remove_duplicated_tag: bool,
        batch_output_save_json: bool,

        interrogator: Interrogator,

        threshold: float,
        character_threshold: float,

        add_rating_tag: bool,
        add_model_tag: bool,

        additional_tags: str,
        exclude_tags: str,
        sort_by_alphabetical_order: bool,
        add_confident_as_weight: bool,
        replace_underscore: bool,
        replace_underscore_excludes: str,
        escape_tag: bool,

        unload_model_after_running: bool,
        progress_model_key: str | None = None,
):
    postprocess_opts = (
        threshold,
        character_threshold,
        add_rating_tag,
        add_model_tag,
        split_str(additional_tags),
        split_str(exclude_tags),
        sort_by_alphabetical_order,
        add_confident_as_weight,
        replace_underscore,
        split_str(replace_underscore_excludes),
        escape_tag
    )

    # batch process
    batch_input_glob = batch_input_glob.strip()
    batch_output_dir = batch_output_dir.strip()
    batch_output_filename_format = batch_output_filename_format.strip()

    if batch_input_glob != '':
        # if there is no glob pattern, insert it automatically
        if not batch_input_glob.endswith('*'):
            if not batch_input_glob.endswith(os.sep):
                batch_input_glob += os.sep
            batch_input_glob += '*'

        if batch_input_recursive:
            batch_input_glob += '*'

        # get root directory of input glob pattern
        base_dir = batch_input_glob.replace('?', '*')
        base_dir = base_dir.split(os.sep + '*').pop(0)

        # check the input directory path
        if not os.path.isdir(base_dir):
            print('input path is not a directory / 输入的路径不是文件夹，终止识别')
            if progress_model_key:
                tagger_progress.finish_error('input path is not a directory')
            return 'input path is not a directory'

        # this line is moved here because some reason
        # PIL.Image.registered_extensions() returns only PNG if you call too early
        supported_extensions = [
            e
            for e, f in Image.registered_extensions().items()
            if f in Image.OPEN
        ]

        paths = [
            Path(p)
            for p in glob(batch_input_glob, recursive=batch_input_recursive)
            if '.' + p.split('.').pop().lower() in supported_extensions
        ]

        print(f'found {len(paths)} image(s)')

        if progress_model_key:
            tagger_progress.begin_tagging(progress_model_key, len(paths))

        try:
            for index, path in enumerate(paths, start=1):
                if progress_model_key:
                    tagger_progress.check_cancelled()
                    tagger_progress.set_tagging(index, len(paths), path.name)
                try:
                    image = Image.open(path)
                except UnidentifiedImageError:
                    # just in case, user has mysterious file...
                    print('unsupported image type / 图片格式不受支持')
                    continue

                # guess the output path
                base_dir_last = Path(base_dir).parts[-1]
                base_dir_last_idx = path.parts.index(base_dir_last)
                output_dir = Path(
                    batch_output_dir) if batch_output_dir else Path(base_dir)
                output_dir = output_dir.joinpath(
                    *path.parts[base_dir_last_idx + 1:]).parent

                output_dir.mkdir(0o777, True, True)

                # format output filename
                format_info = format.Info(path, 'txt')

                try:
                    formatted_output_filename = format.pattern.sub(
                        lambda m: format.format(m, format_info),
                        batch_output_filename_format
                    )
                except (TypeError, ValueError) as error:
                    return str(error)

                output_path = output_dir.joinpath(
                    formatted_output_filename
                )

                output = []
                from mikazuki.tagger.caption_job import CaptionJobManager, CaptionWriteConflict, caption_sha256, write_caption_atomic
                from mikazuki.dataset_editor import detect_caption_format
                from mikazuki.llm.runtime import caption_job_store
                before_hash = caption_sha256(output_path)
                if output_path.is_symlink():
                    raise CaptionWriteConflict("caption symlink cannot be overwritten")

                if output_path.is_file():
                    output.append(output_path.read_text(errors='ignore').strip())

                    if batch_output_action_on_conflict == 'ignore':
                        print('skipping existing caption / 跳过已有 caption')
                        continue
                    known_format = caption_job_store.find_format(output_path, before_hash) or detect_caption_format(output[0])
                    if batch_output_action_on_conflict in {'prepend', 'append'} and output[0] and known_format != 'tag':
                        if unload_model_after_running:
                            interrogator.unload()
                        return 'Tag merge cannot modify natural or mixed caption'

                tags = interrogator.interrogate(image)
                processed_tags = Interrogator.postprocess_tags(
                    tags,
                    *postprocess_opts
                )

                # TODO: switch for less print
                print(
                    f'found {len(processed_tags)} tags out of {len(tags)}'
                )

                plain_tags = ', '.join(processed_tags)

                if batch_output_action_on_conflict == 'copy':
                    output = [plain_tags]
                elif batch_output_action_on_conflict == 'prepend':
                    output.insert(0, plain_tags)
                else:
                    output.append(plain_tags)

                if batch_remove_duplicated_tag:
                    CaptionJobManager._guard_path(path)
                    write_caption_atomic(output_path,
                        ', '.join(
                            OrderedDict.fromkeys(
                                map(str.strip, ','.join(output).split(','))
                            )
                        ),
                        expected_sha256=before_hash, trailing_newline=False,
                    )
                else:
                    CaptionJobManager._guard_path(path)
                    write_caption_atomic(output_path,
                        ', '.join(output),
                        expected_sha256=before_hash, trailing_newline=False,
                    )

                if batch_output_save_json:
                    output_path.with_suffix('.json').write_text(
                        json.dumps(tags)
                    )

            print('all done / 识别完成')
        except TaggerCancelled:
            print('tagging cancelled / 打标已中止')
            if unload_model_after_running:
                interrogator.unload()
            return 'Cancelled'
        except Exception:
            if unload_model_after_running:
                interrogator.unload()
            raise

    if unload_model_after_running:
        interrogator.unload()

    return 'Succeed'
