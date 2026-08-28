"""AI Toolkit engine pack: FLUX.2 Klein LoRA training via ostris/ai-toolkit.

First supported train types: Klein base 4B / 9B LoRA (klein-4b-lora, klein-9b-lora).
"""

from .manifest import TRAIN_TYPES as TRAIN_TYPE_MAP

TRAIN_TYPES = tuple(TRAIN_TYPE_MAP)
