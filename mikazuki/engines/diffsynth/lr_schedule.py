"""LR policies for the pinned upstream loop, counted in optimizer updates."""
import math

POLICIES = ('constant', 'linear', 'cosine', 'cosine_with_restarts')


def nonnegative_int(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} 必须是非负整数')
    try:
        number = int(value)
        if number < 0 or number != float(value):
            raise ValueError()
        return number
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f'{name} 必须是非负整数') from exc


def schedule_config(config, total_steps):
    policy = config.get('lr_scheduler', 'constant')
    if policy not in POLICIES:
        raise ValueError('不支持的学习率调度器')
    warmup = nonnegative_int(config.get('lr_warmup_steps', 0), '预热步数')
    restarts = nonnegative_int(config.get('lr_restart_count', 1), '重启次数') if policy == 'cosine_with_restarts' else 0
    if warmup >= total_steps:
        raise ValueError(f'预热步数必须小于总优化器更新次数 {total_steps}')
    if policy == 'cosine_with_restarts' and restarts >= total_steps - warmup:
        raise ValueError('余弦周期数不能超过预热后的更新次数')
    return dict(policy=policy, warmup_steps=warmup, restart_count=restarts, total_steps=total_steps)


def lr_factor(step, *, policy, warmup_steps, restart_count, total_steps):
    if step < warmup_steps:
        return step / warmup_steps
    if policy == 'constant':
        return 1.0
    progress = min(1.0, max(0.0, (step - warmup_steps) / (total_steps - warmup_steps)))
    if policy == 'linear':
        return 1.0 - progress
    if progress >= 1:
        return 0.0
    if policy == 'cosine_with_restarts':
        progress = (progress * (restart_count + 1)) % 1.0
    return 0.5 * (1 + math.cos(math.pi * progress))


def launch_with_schedule(accelerator, dataset, model, logger, args, settings):
    """Replace only the scheduler factory in an isolated upstream function.

    Keep the pinned training loop, accumulation and offload code unchanged.
    Neither torch nor the imported upstream module is monkey-patched globally.
    """
    import torch
    import types
    from functools import partial
    from diffsynth.diffusion.runner import launch_training_task

    class Overlay:
        def __init__(self, original, **overrides):
            self.original, self.overrides = original, overrides

        def __getattr__(self, name):
            return self.overrides[name] if name in self.overrides else getattr(self.original, name)

    def create_scheduler(optimizer):
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, partial(lr_factor, **settings))
        logger.lr_scheduler = scheduler
        # Log the rate actually used, before the runner advances the scheduler.
        optimizer.register_step_pre_hook(lambda opt, _args, _kwargs: setattr(logger, 'last_learning_rate', opt.param_groups[0]['lr']))
        return scheduler

    globals_copy = dict(launch_training_task.__globals__)
    upstream_offload_manager = globals_copy['OffloadTrainingManager']

    def create_offload_manager(model, *positional, **kwargs):
        manager = upstream_offload_manager(model, *positional, **kwargs)
        model._preview_offload_manager = manager
        return manager

    globals_copy['OffloadTrainingManager'] = create_offload_manager
    class EpochDataLoader(torch.utils.data.DataLoader):
        def __iter__(self):
            if hasattr(self.dataset, 'shuffle_batches'):
                self.dataset.shuffle_batches()
            return super().__iter__()
    globals_copy['torch'] = Overlay(torch, optim=Overlay(torch.optim,
        lr_scheduler=Overlay(torch.optim.lr_scheduler, ConstantLR=create_scheduler)),
        utils=Overlay(torch.utils, data=Overlay(torch.utils.data, DataLoader=EpochDataLoader)))
    run = types.FunctionType(launch_training_task.__code__, globals_copy,
                             launch_training_task.__name__, launch_training_task.__defaults__, launch_training_task.__closure__)
    run.__kwdefaults__ = launch_training_task.__kwdefaults__
    print(f'[lr schedule] {settings}', flush=True)
    for key, value in settings.items():
        setattr(args, 'lr_' + key, value)
    return run(accelerator, dataset, model, logger, args=args)
