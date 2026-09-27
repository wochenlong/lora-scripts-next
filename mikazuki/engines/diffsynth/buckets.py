"""Kohya bucket geometry, without importing its training runtime.

Ported from vendor/sd-scripts/library/{train_util,model_util,utils}.py.
Uses the same nearest-aspect buckets, rounding, AREA/LANCZOS and center crop.
"""
import math
import re
from collections import Counter
from pathlib import Path
from PIL import Image


def bucket_settings(config):
    from .lr_schedule import nonnegative_int
    result = {key: nonnegative_int(config.get(key, default), key) for key, default in
              [('min_bucket_reso', 256), ('max_bucket_reso', 2048), ('bucket_reso_steps', 64)]}
    if config.get('resolution') not in (None, ''):
        parts = re.split(r'[,xX×，]', str(config['resolution']).strip())
        if len(parts) == 1:
            parts *= 2
        if len(parts) != 2:
            raise ValueError('分辨率请填写 宽,高，例如 1024,1024')
        dimensions = [nonnegative_int(p.strip(), '分辨率') for p in parts]
        if any(n < 64 or n % 64 for n in dimensions):
            raise ValueError('基准分辨率宽高必须是至少 64 的 64 倍数')
        result['max_pixels'] = math.prod(dimensions)
    else:
        result['max_pixels'] = nonnegative_int(config.get('max_pixels', 1048576), 'max_pixels')
        dimensions = [math.sqrt(result['max_pixels'])] * 2
    result['resolution'] = [int(n) for n in dimensions]
    result['enable_bucket'] = bool(config.get('enable_bucket', True))
    result['bucket_no_upscale'] = bool(config.get('bucket_no_upscale', False))
    if not result['enable_bucket']:
        return result
    step = result['bucket_reso_steps']
    if step < 32 or step % 32:
        raise ValueError('Qwen 分桶步长必须为 32 的正整数倍')
    if result['max_pixels'] < step * step:
        raise ValueError('最大像素面积不能小于一个分辨率桶单元')
    if not result['bucket_no_upscale']:
        lo, hi = result['min_bucket_reso'], result['max_bucket_reso']
        if lo < step or lo % step or hi % step or hi < max(lo, *dimensions):
            raise ValueError('桶边长必须是步长的倍数，最大桶边长不能小于基准分辨率或最小桶边长')
    return result


def select_bucket(width, height, settings):
    area, step = settings['max_pixels'], settings['bucket_reso_steps']
    aspect = width / height
    if not settings.get('enable_bucket', True):
        target_width, target_height = width, height
        if width * height > area:
            scale = math.sqrt(width * height / area)
            target_width, target_height = int(width / scale), int(height / scale)
        reso = (target_width // 32 * 32, target_height // 32 * 32)
        if min(reso) == 0:
            raise ValueError('图片短边过小，无法对齐到 32 像素')
        scale = max(reso[0] / width, reso[1] / height)
        return reso, (round(width * scale), round(height * scale))
    if not settings['bucket_no_upscale']:
        lo, hi = settings['min_bucket_reso'], settings['max_bucket_reso']
        side = int(math.sqrt(area) // step) * step
        resolutions = {(side, side)}
        for w in range(lo, hi + 1, step):
            h = min(hi, int((area // w) // step) * step)
            if h >= lo:
                resolutions.update(((w, h), (h, w)))
        ordered = sorted(resolutions)
        reso = (width, height) if (width, height) in resolutions else min(ordered, key=lambda r: abs(r[0] / r[1] - aspect))
        scale = reso[1] / height if aspect > reso[0] / reso[1] else reso[0] / width
        resized = (int(width * scale + .5), int(height * scale + .5))
    else:
        if width * height > area:
            def rounded(x):
                return int(x + .5) // step * step
            rw = math.sqrt(area * aspect)
            rh = area / rw
            bw, bh = rounded(rw), rounded(rh)
            hwr, whr = rounded(bw / aspect), rounded(bh * aspect)
            if min(bw, bh, hwr, whr) == 0:
                raise ValueError('图片比例过于极端，无法生成有效桶')
            if abs(bw / hwr - aspect) < abs(whr / bh - aspect):
                resized = (bw, int(bw / aspect + .5))
            else:
                resized = (int(bh * aspect + .5), bh)
        else:
            resized = (width, height)
        reso = tuple(n // step * step for n in resized)
    if min(reso) == 0:
        raise ValueError('图片短边小于桶步长；请降低桶步长或允许放大')
    return reso, resized


def dataset_buckets(rows, base, settings, repeat, batch_size):
    sizes = []
    for row in rows:
        with Image.open(Path(base) / row['image']) as image:
            sizes.append(select_bucket(*image.size, settings)[0])
    counts = Counter(sizes)
    batches = sum(math.ceil(n * repeat / batch_size) for n in counts.values())
    return sizes, batches, [{'width': w, 'height': h, 'images': n * repeat,
                            'batches': math.ceil(n * repeat / batch_size)} for (w, h), n in sorted(counts.items())]


class BucketImageLoader:
    def __init__(self, base, settings):
        self.base, self.settings = Path(base), settings

    def __call__(self, path):
        import cv2
        import numpy as np
        with Image.open(self.base / path) as original:
            image = original.convert('RGBA')
        if not self.settings.get('enable_bucket', True):
            from diffsynth.core.data.operators import ImageCropAndResize
            return ImageCropAndResize(max_pixels=self.settings['max_pixels'],
                height_division_factor=32, width_division_factor=32)(image)
        width, height = image.size
        reso, resized = select_bucket(width, height, self.settings)
        if resized != image.size:
            if width >= resized[0] and height >= resized[1]:
                image = Image.fromarray(cv2.resize(np.asarray(image), resized, interpolation=cv2.INTER_AREA))
            else:
                image = image.resize(resized, Image.Resampling.LANCZOS)
        x, y = (resized[0] - reso[0]) // 2, (resized[1] - reso[1]) // 2
        return image.crop((x, y, x + reso[0], y + reso[1]))


def batched_dataset(dataset, sizes, batch_size):
    import torch
    import random
    from collections import defaultdict

    class Batches(torch.utils.data.Dataset):
        load_from_cache = True

        def __init__(self):
            self.buckets = defaultdict(list)
            self.reported_sizes = set()
            for i in range(len(dataset)):
                self.buckets[sizes[i % len(sizes)]].append(i)
            self.shuffle_batches()

        def shuffle_batches(self):
            self.groups = []
            for indices in self.buckets.values():
                indices = indices.copy()
                random.shuffle(indices)
                self.groups.extend(indices[i:i + batch_size] for i in range(0, len(indices), batch_size))

        def __len__(self):
            return len(self.groups)

        def __getitem__(self, index):
            rows = [dataset[i] for i in self.groups[index]]
            shared = dict(rows[0][0])
            shared['input_latents'] = torch.cat([r[0]['input_latents'] for r in rows])
            length = max(r[1]['prompt_embeds'].shape[1] for r in rows)
            tensors, masks = [], []
            for _, text, _ in rows:
                embedding = text['prompt_embeds']
                n = embedding.shape[1]
                tensors.append(torch.nn.functional.pad(embedding, (0, 0, 0, length - n)))
                mask = text['prompt_embeds_mask']
                mask = torch.ones(1, n, dtype=torch.bool) if mask is None else mask.bool()
                masks.append(torch.nn.functional.pad(mask, (0, length - n)))
                if text['edit_image_pad_mask'].any():
                    raise ValueError('当前分桶 batch 仅支持文生图')
            # Image/text positions are shared across rows; validity differs per row.
            positive = dict(prompt_embeds=torch.cat(tensors), prompt_embeds_mask=torch.cat(masks),
                            edit_image_pad_mask=torch.zeros(1, length, dtype=torch.bool))
            if len(rows) not in self.reported_sizes:
                print(f'[batch] images={len(rows)}, latents={list(shared["input_latents"].shape)}, text={list(positive["prompt_embeds"].shape)}', flush=True)
                self.reported_sizes.add(len(rows))
            return shared, positive, {}
    return Batches()
