"""Use the upstream logger hooks; leave its optimizer and training loop intact."""
import copy
import json
from pathlib import Path
import random
from functools import partial

import numpy as np
import torch
from diffsynth.diffusion import ModelLogger
from .formats import export_comfy_lora


class QwenLogger(ModelLogger):
    def __init__(self, output_path, samples, output_name, alpha=None, sample_callback=None, batches_per_epoch=None):
        super().__init__(output_path, remove_prefix_in_ckpt='pipe.dit.', state_dict_converter=partial(export_comfy_lora, alpha=alpha),
                         enable_csv_log=True, enable_tensorboard_log=True)
        self.samples, self.output_name = samples, output_name
        self.pending_loss, self.microsteps = 0.0, 0
        self.sample_callback = sample_callback
        self.batches_seen, self.batches_per_epoch = 0, batches_per_epoch
        if samples.get('every_epochs') is not None and not batches_per_epoch:
            raise ValueError('按 epoch 预览需要实际每轮 batch 数')

    def on_step_end(self, accelerator, model, save_steps=None, **kwargs):
        self.batches_seen += 1
        self.pending_loss += float(kwargs['loss'].detach().float())
        self.microsteps += 1
        if not accelerator.sync_gradients:
            return
        loss = self.pending_loss / self.microsteps
        self.pending_loss, self.microsteps = 0.0, 0
        if accelerator.optimizer_step_was_skipped:
            return
        super().on_step_end(accelerator, model, save_steps, loss=loss)
        if hasattr(self, 'last_learning_rate'):
            for metric_logger in self.loggers:
                metric_logger.log('learning_rate', self.last_learning_rate, self.num_steps)
        if self.samples['enabled']:
            every_epochs = self.samples.get('every_epochs')
            if every_epochs is not None:
                epoch_end = self.batches_seen % self.batches_per_epoch == 0
                epoch = self.batches_seen // self.batches_per_epoch
                due = epoch_end and epoch % every_epochs == 0
            else:
                due = self.num_steps % self.samples['every_steps'] == 0
            if due:
                self.sample(accelerator.unwrap_model(model))

    def save_model(self, accelerator, model, file_name):
        super().save_model(accelerator, model, self.output_name + '-' + file_name)

    def write_phase(self, path, phase):
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'phase': phase, 'step': self.num_steps}), encoding='utf-8')
        temporary.replace(path)

    def sample(self, model):
        pipe = model.pipe
        scheduler = pipe.scheduler
        modes = [(module, module.training) for module in model.modules()]
        rng_python, rng_numpy = random.getstate(), np.random.get_state()
        directory = Path(self.output_path) / 'sample'
        directory.mkdir(parents=True, exist_ok=True)
        status = Path(self.output_path) / 'phase.json'
        self.write_phase(status, 'sampling')
        print(f'[sampling] optimizer_step={self.num_steps}', flush=True)
        try:
            with torch.random.fork_rng(), torch.no_grad():
                pipe.scheduler = copy.deepcopy(scheduler)
                model.eval()
                for index, sample in enumerate(self.samples['samples']):
                    if self.sample_callback is not None:
                        image = self.sample_callback(model, sample)
                    else:
                        image = pipe(prompt=sample['prompt'], width=sample['width'], height=sample['height'], seed=sample['seed'],
                                     cfg_scale=sample['guidance_scale'], num_inference_steps=sample['sample_steps'], tiled=True)
                    path = directory / f'{self.output_name}-step-{self.num_steps:08d}-sample-{index + 1:02d}.png'
                    temporary = path.with_suffix('.tmp')
                    image.save(temporary, format='PNG')
                    temporary.replace(path)
                    path.with_suffix('.json').write_text(json.dumps({'step': self.num_steps, 'sample_id': index + 1, **sample}, ensure_ascii=False), encoding='utf-8')
                    del image
        except Exception:
            self.write_phase(status, 'sampling_failed')
            # A failed preview fails the task visibly; never silently skip samples.
            raise
        else:
            self.write_phase(status, 'training')
        finally:
            pipe.scheduler = scheduler
            for module, training in modes:
                module.training = training
            random.setstate(rng_python)
            np.random.set_state(rng_numpy)
        print(f'[sampling complete] optimizer_step={self.num_steps}', flush=True)
