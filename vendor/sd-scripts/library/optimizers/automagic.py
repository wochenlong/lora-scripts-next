# Ported from ostris/ai-toolkit (MIT License)
# https://github.com/ostris/ai-toolkit/blob/main/toolkit/optimizers/automagic.py
# Copyright (c) ostris. Used under MIT License.
from typing import List
import torch
from library.optimizers.optimizer_utils import Auto8bitTensor, copy_stochastic, stochastic_grad_accummulation

try:
    from optimum.quanto import QBytesTensor
    _QUANTO_AVAILABLE = True
except ImportError:
    QBytesTensor = None
    _QUANTO_AVAILABLE = False


class Automagic(torch.optim.Optimizer):
    def __init__(
        self,
        params,
        lr=1e-6,
        min_lr=1e-7,
        max_lr=1e-3,
        lr_bump=1e-6,
        eps=(1e-30, 1e-3),
        clip_threshold=1.0,
        beta2=0.999,
        weight_decay=0.0,
        do_paramiter_swapping=False,
        paramiter_swapping_factor=0.1,
    ):
        self.lr = lr
        if self.lr > 1e-3:
            print(f"Warning! Start lr is very high: {self.lr}. Forcing to 1e-6.")
            self.lr = 1e-6
        self.min_lr = min_lr
        self.max_lr = max_lr
        self.lr_bump = lr_bump

        defaults = {
            "lr": lr,
            "eps": eps,
            "clip_threshold": clip_threshold,
            "beta2": beta2,
            "weight_decay": weight_decay,
        }
        super().__init__(params, defaults)

        self.base_lrs: List[float] = [lr for group in self.param_groups]
        self.is_stochastic_rounding_accumulation = False

        for group in self.param_groups:
            for param in group['params']:
                if param.requires_grad and param.dtype != torch.float32:
                    self.is_stochastic_rounding_accumulation = True
                    param.register_post_accumulate_grad_hook(stochastic_grad_accummulation)

        self.do_paramiter_swapping = do_paramiter_swapping
        self.paramiter_swapping_factor = paramiter_swapping_factor
        self._total_paramiter_size = sum(
            torch.numel(p) for group in self.param_groups for p in group['params']
        )
        print(f"Automagic: total training parameters: {self._total_paramiter_size:,}")

        if self.do_paramiter_swapping:
            self.enable_paramiter_swapping(self.paramiter_swapping_factor)

    def enable_paramiter_swapping(self, paramiter_swapping_factor=0.1):
        self.do_paramiter_swapping = True
        self.paramiter_swapping_factor = paramiter_swapping_factor
        self.swap_paramiters()

    def swap_paramiters(self):
        import random
        all_params = []
        for group in self.param_groups:
            for param in group['params']:
                param.requires_grad_(False)
                param.grad = None
                all_params.append(param)
        random.shuffle(all_params)

        target = int(self._total_paramiter_size * self.paramiter_swapping_factor)
        total = 0
        for param in all_params:
            total += torch.numel(param)
            if total >= target:
                break
            else:
                param.requires_grad_(True)

    @staticmethod
    def _get_lr(param_group, param_state):
        return param_state.get("avg_lr", 0.0)

    def _get_group_lr(self, group):
        lrs = [self._get_lr(group, self.state[p]) for p in group["params"]]
        return sum(lrs) / len(lrs) if lrs else self.lr

    @staticmethod
    def _rms(tensor):
        return tensor.norm(2) / (tensor.numel() ** 0.5)

    @staticmethod
    def _approx_sq_grad(exp_avg_sq_row, exp_avg_sq_col):
        r_factor = (exp_avg_sq_row / exp_avg_sq_row.mean(dim=-1, keepdim=True)).rsqrt_().unsqueeze(-1)
        c_factor = exp_avg_sq_col.unsqueeze(-2).rsqrt()
        return torch.mul(r_factor, c_factor)

    def step_hook(self):
        if not self.is_stochastic_rounding_accumulation:
            return
        for group in self.param_groups:
            for param in group['params']:
                if param.requires_grad and hasattr(param, "_accum_grad"):
                    param.grad = param._accum_grad
                    del param._accum_grad

    def get_learning_rates(self):
        lrs = [self._get_group_lr(group) for group in self.param_groups]
        return lrs if lrs else self.base_lrs

    def get_avg_learning_rate(self):
        lrs = self.get_learning_rates()
        return sum(lrs) / len(lrs)

    @torch.no_grad()
    def step(self, closure=None):
        self.step_hook()
        loss = None
        if closure is not None:
            loss = closure()

        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None or not p.requires_grad:
                    continue

                grad = p.grad
                if grad.dtype != torch.float32:
                    grad = grad.to(torch.float32)
                if grad.is_sparse:
                    raise RuntimeError("Automagic does not support sparse gradients.")

                state = self.state[p]
                grad_shape = grad.shape
                factored = len(grad_shape) >= 2

                if len(state) == 0:
                    self.initialize_state(p)
                else:
                    if factored:
                        if "exp_avg_sq_row" not in state or "exp_avg_sq_col" not in state:
                            state["exp_avg_sq_row"] = torch.zeros(p.shape[:-1]).to(grad)
                            state["exp_avg_sq_col"] = torch.zeros(p.shape[:-2] + p.shape[-1:]).to(grad)
                        else:
                            state["exp_avg_sq_row"] = state["exp_avg_sq_row"].to(grad)
                            state["exp_avg_sq_col"] = state["exp_avg_sq_col"].to(grad)
                    else:
                        if "exp_avg_sq" not in state:
                            state["exp_avg_sq"] = torch.zeros_like(grad)
                        else:
                            state["exp_avg_sq"] = state["exp_avg_sq"].to(grad)

                p_data_fp32 = p
                if _QUANTO_AVAILABLE and isinstance(p_data_fp32, QBytesTensor):
                    p_data_fp32 = p_data_fp32.dequantize()
                if p.dtype != torch.float32:
                    p_data_fp32 = p_data_fp32.clone().float()

                if "step" not in state:
                    state["step"] = 0
                state["step"] += 1
                state["RMS"] = self._rms(p_data_fp32)

                beta2 = group["beta2"]
                eps = group["eps"]
                if isinstance(eps, (tuple, list)):
                    eps = eps[0]

                update = (grad ** 2) + eps
                if factored:
                    exp_avg_sq_row = state["exp_avg_sq_row"]
                    exp_avg_sq_col = state["exp_avg_sq_col"]
                    exp_avg_sq_row.mul_(beta2).add_(update.mean(dim=-1), alpha=(1.0 - beta2))
                    exp_avg_sq_col.mul_(beta2).add_(update.mean(dim=-2), alpha=(1.0 - beta2))
                    update = self._approx_sq_grad(exp_avg_sq_row, exp_avg_sq_col)
                    update.mul_(grad)
                else:
                    exp_avg_sq = state["exp_avg_sq"]
                    exp_avg_sq.mul_(beta2).add_(update, alpha=(1.0 - beta2))
                    update = exp_avg_sq.rsqrt().mul_(grad)

                update.div_((self._rms(update) / group["clip_threshold"]).clamp_(min=1.0))

                if 'last_polarity' not in state or 'lr_mask' not in state:
                    self.initialize_state(p)

                last_polarity = state['last_polarity']
                current_polarity = (update > 0).to(torch.bool)
                sign_agreement = torch.where(last_polarity == current_polarity, 1, -1)
                state['last_polarity'] = current_polarity

                lr_mask = state['lr_mask'].to(torch.float32)
                new_lr = torch.where(
                    sign_agreement > 0,
                    lr_mask + self.lr_bump,
                    lr_mask - self.lr_bump,
                )
                new_lr = torch.clamp(new_lr, min=self.min_lr, max=self.max_lr)
                update.mul_(new_lr)

                state['lr_mask'] = Auto8bitTensor(new_lr)
                state['avg_lr'] = torch.mean(new_lr)

                if group["weight_decay"] != 0:
                    weight_decay_update = p_data_fp32 * (-group["weight_decay"]) * new_lr
                    p_data_fp32.add_(weight_decay_update)

                p_data_fp32.add_(-update)

                if p.dtype != torch.float32:
                    copy_stochastic(p, p_data_fp32)

        return loss

    def initialize_state(self, p):
        state = self.state[p]
        state["step"] = 0
        if 'lr_mask' not in state:
            state['lr_mask'] = Auto8bitTensor(
                torch.ones(p.shape).to(p.device, dtype=torch.float32) * self.lr
            )
        state['avg_lr'] = torch.mean(state['lr_mask'].to(torch.float32))
        if 'last_polarity' not in state:
            state['last_polarity'] = torch.zeros(p.shape, dtype=torch.bool, device=p.device)
        factored = len(p.shape) >= 2
        if factored:
            state["exp_avg_sq_row"] = torch.zeros(p.shape[:-1]).to(p)
            state["exp_avg_sq_col"] = torch.zeros(p.shape[:-2] + p.shape[-1:]).to(p)
        else:
            state["exp_avg_sq"] = torch.zeros_like(p)
        state["RMS"] = 0

    def state_dict(self, *args, **kwargs):
        orig = super().state_dict(*args, **kwargs)
        new_state = {}
        for p, state in orig['state'].items():
            s = {k: v for k, v in state.items() if k != 'lr_mask'}
            if 'lr_mask' in state:
                s['lr_mask'] = state['lr_mask'].state_dict()
            new_state[p] = s
        orig['state'] = new_state
        return orig

    def load_state_dict(self, state_dict, strict=True):
        is_valid = any(
            'lr_mask' in pstate
            for pstate in state_dict.get('state', {}).values()
            if isinstance(pstate, dict)
        )
        if not is_valid:
            return

        stripped = {
            'state': {pid: {k: v for k, v in ps.items() if k != 'lr_mask'}
                      for pid, ps in state_dict['state'].items()},
            'param_groups': state_dict['param_groups'],
        }
        super().load_state_dict(stripped)

        # torch packs optimizer state with dense indices over ALL params in
        # param_groups order; params that never received a gradient (e.g. text
        # encoder LoRA with cached TE outputs) have no entry. Map lr_mask by the
        # same packed index, never by a requires_grad-filtered position, or every
        # param after a skipped one gets the previous param's mask.
        all_params = [p for g in self.param_groups for p in g['params']]
        for i, param in enumerate(all_params):
            if i not in state_dict['state']:
                continue
            saved = state_dict['state'][i]
            if 'lr_mask' not in saved:
                continue
            if param not in self.state:
                self.initialize_state(param)
            try:
                lm = saved['lr_mask']
                if 'quantized' in lm and lm['quantized'].shape == param.shape:
                    # accelerate loads optimizer state with map_location="cpu"; the
                    # reconstructed mask must follow the param device or the next
                    # step() crashes with a cuda/cpu device mismatch
                    mask = Auto8bitTensor(lm)
                    mask.quantized = mask.quantized.to(param.device)
                    self.state[param]['lr_mask'] = mask
                else:
                    raise ValueError(
                        f"shape mismatch (saved {tuple(lm['quantized'].shape) if 'quantized' in lm else 'unknown'}"
                        f" vs current {tuple(param.shape)})"
                    )
            except Exception as e:
                print(f"Automagic: reinit lr_mask for param {i}: {e}")
                self.state[param]['lr_mask'] = Auto8bitTensor(
                    torch.ones(param.shape).to(param.device, dtype=torch.float32) * self.lr
                )
