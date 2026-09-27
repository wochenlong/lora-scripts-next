"""Reference images use the pinned pipeline's geometry and encoding contract."""
from PIL import Image


def load_references(paths):
    images = []
    for path in paths:
        with Image.open(path) as image:
            images.append(image.convert('RGBA'))
    return images or None


def resized_references(pipe, images, width, height):
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Unit_EditImageEmbedder
    return QwenImage21Unit_EditImageEmbedder().resize_edit_image(pipe, images, width * height)
