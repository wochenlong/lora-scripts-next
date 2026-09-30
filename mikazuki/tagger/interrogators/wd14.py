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
from mikazuki.tagger.interrogators.base import Interrogator
from mikazuki.tagger import dbimutils, format
from mikazuki.tagger.local_models import local_model_asset_paths
from mikazuki.tagger.ort_session import create_inference_session


class WaifuDiffusionInterrogator(Interrogator):
    def __init__(
            self,
            name: str,
            model_path='model.onnx',
            tags_path='selected_tags.csv',
            local_model_aliases: tuple[str, ...] = (),
            **kwargs
    ) -> None:
        super().__init__(name)
        self.model_path = model_path
        self.tags_path = tags_path
        self.local_model_aliases = tuple(local_model_aliases)
        self.kwargs = kwargs

    def download(self) -> Tuple[os.PathLike, os.PathLike]:
        for model_key in (self.name, *self.local_model_aliases):
            local_paths = local_model_asset_paths(model_key, self)
            if local_paths:
                print(
                    f"Loading {self.name} model from local tagger-models "
                    f"directory ({model_key})"
                )
                return local_paths

        repo_id = self.kwargs["repo_id"]
        cache_kwargs = dict(self.kwargs)
        cache_kwargs["local_files_only"] = True
        try:
            model_path = Path(hf_hub_download(
                **cache_kwargs, filename=self.model_path))
            tags_path = Path(hf_hub_download(
                **cache_kwargs, filename=self.tags_path))
            print(f"Loading {self.name} model from local Hugging Face cache")
            return model_path, tags_path
        except Exception:
            pass

        print(f"Loading {self.name} model from {repo_id} (first run may download ~400MB, see console log)")

        model_path = Path(hf_hub_download(
            **self.kwargs, filename=self.model_path))
        tags_path = Path(hf_hub_download(
            **self.kwargs, filename=self.tags_path))
        return model_path, tags_path

    def load(self) -> None:
        model_path, tags_path = self.download()

        # only one of these packages should be installed at a time in any one environment
        # https://onnxruntime.ai/docs/get-started/with-python.html#install-onnx-runtime
        # TODO: remove old package when the environment changes?
        # from mikazuki.launch_utils import is_installed, run_pip
        # if not is_installed('onnxruntime'):
        #     package = os.environ.get(
        #         'ONNXRUNTIME_PACKAGE',
        #         'onnxruntime-gpu'
        #     )

        #     run_pip(f'install {package}', 'onnxruntime')

        # Load torch to load cuda libs built in torch for onnxruntime; torch is
        # optional now that training stacks live in engine venvs.
        try:
            import torch  # noqa: F401
        except ImportError:
            pass

        self.model = create_inference_session(model_path)

        print(f'Loaded {self.name} model from {model_path}')

        self.tags = pd.read_csv(tags_path)

    def interrogate(
            self,
            image: Image
    ) -> Dict[str, List[Tuple[str, float]]]:
        # init model
        if not hasattr(self, 'model') or self.model is None:
            self.load()

        # code for converting the image and running the model is taken from the link below
        # thanks, SmilingWolf!
        # https://huggingface.co/spaces/SmilingWolf/wd-v1-4-tags/blob/main/app.py

        # convert an image to fit the model
        _, height, _, _ = self.model.get_inputs()[0].shape

        # alpha to white
        image = image.convert('RGBA')
        new_image = Image.new('RGBA', image.size, 'WHITE')
        new_image.paste(image, mask=image)
        image = new_image.convert('RGB')
        image = np.asarray(image)

        # PIL RGB to OpenCV BGR
        image = image[:, :, ::-1]

        image = dbimutils.make_square(image, height)
        image = dbimutils.smart_resize(image, height)
        image = image.astype(np.float32)
        image = np.expand_dims(image, 0)

        # evaluate model
        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        confidents = self.model.run([label_name], {input_name: image})[0]

        tags = self.tags[:][['name']]
        tags['confidents'] = confidents[0]

        # first 4 items are for rating (general, sensitive, questionable, explicit)
        ratings = dict(tags[:4].values)

        # rest are regular tags
        tags = dict(tags[4:].values)

        result = {
            "rating": [],
            "general": [],
            "character": [],
            "copyright": [],
            "artist": [],
            "meta": [],
            "quality": [],
            "model": []
        }

        for tag, conf in ratings.items():
            result["rating"].append((tag, conf))

        for tag, conf in tags.items():
            result["general"].append((tag, conf))

        return result
