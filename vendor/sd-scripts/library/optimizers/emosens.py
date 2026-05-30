import torch
from torch.optim import Optimizer
import math

"""
EmoSens v3.9.1 (260520) Standard Edition ECC版(CPU-GPUデータ転送対応含む)
shadow-system v3.1 -moment v3.1 emoPulse v3.9 FFT-Swap-Aware dNR-converge
|学習率推奨値| LoRA:1.0 |FFT/Full-Fine-Tuning| Transformer:0.01, UNET:0.1, etc...
全層同一LRのため Transformer 等では発散しやすい(FFTは難しい) 事前学習やLoRA等が望ましいです
これまでの emo系 v3.7～3.8 継承、早期停止関連の効率化やコード修正やコメント最適化等を実施
Early Stop 判定通知の動的最適化、dNR活用で収束点をユーザー任意で明確化できる(stopcoef)
### FFT適応 cuDNN 等でデータ配置を求める仕様により中間テンソル(コピー)生じる(VRAM負荷増) ###
"""

# ECC - emo closure capture (Loss-Bypass)
if not hasattr(torch.optim.Optimizer, "_manual_loss"):
    torch.optim.Optimizer._manual_loss = 0.0

    # backward-cap (一度だけ実行されるようにする)
    _old_backward = torch.Tensor.backward
    def _new_backward(self, *args, **kwargs):
        if self.ndim == 0:
            try:
                torch.optim.Optimizer._manual_loss = self.item()
            except:
                pass
        return _old_backward(self, *args, **kwargs)
    torch.Tensor.backward = _new_backward
    print("🚩 emo-optim success ecc system ...")

class EmoSens(Optimizer):    # クラス定義＆初期化
    def __init__(self, params,
                 lr=1.0,
                 eps=1e-8,
                 betas=(0.9, 0.995),
                 weight_decay=0.01,
                 stopcoef=0.04,
                 use_shadow:bool=False,
                 notify:bool=True):
        defaults = dict(lr=lr, betas=betas, eps=eps, weight_decay=weight_decay)
        super().__init__(params, defaults)
        self._init_lr = lr
        self.notify = notify         # 収束･安定の通知切替
        self.should_stop = False     # 停止フラグの初期化
        self.stopcoef = stopcoef     # 収束目標値(ユーザー指定可)
        self.use_shadow = use_shadow # 🔸shadow(通常 False)
        self.emoScope = lr           # 動的学習率の調和とリズム

        # shadow は solver 等の特殊用途時に必要かもしれない (optimizerとしては通常不要)
        # use_shadow 緊急時モデル保護：通常 False (将来の特殊アーキテクチャへの保護機能)
        # notify 収束通知の切替え：通常 True (通知不要な場合は False にできる)
        # stopcoef 収束目標Loss：通常 0.04[予兆] (ユーザーの好みで仕上げる)

        self.base_scale, self.max_lim, self.min_lim = 1e-4, 3e-3, 1e-8
        self.dNR_hist, self.noise_est, self.d_est, self.c_est = 1.0, 1.0, 0.02, 0.0
            
    # 学習の引き継ぎ可能(状態保存対応)／収束を深めたい場合に役立つ
    def state_dict(self):
        state_dict = super().state_dict()
        state_dict['emo_internal'] = {
            'emoScope': self.emoScope,
            'dNR_hist': self.dNR_hist,
            'noise_est': self.noise_est,
            'd_est': self.d_est,
            'c_est': self.c_est,
            'should_stop': self.should_stop,
            'stopcoef': self.stopcoef,
        }
        return state_dict

    def load_state_dict(self, state_dict):
        emo_internal = state_dict.pop('emo_internal', None)
        if emo_internal:
            self.emoScope = emo_internal.get('emoScope', self._init_lr)
            self.dNR_hist = emo_internal.get('dNR_hist', 1.0)
            self.noise_est = emo_internal.get('noise_est', 1.0)
            self.d_est = emo_internal.get('d_est', 0.02)
            self.c_est = emo_internal.get('c_est', 0.0)
            self.should_stop = emo_internal.get('should_stop', False)
            self.stopcoef =  emo_internal.get('stopcoef', self.stopcoef)
        super().load_state_dict(state_dict)

    # 感情EMA更新(緊張と安静)／３次４次５次モーメント近似相当(感覚神経系)
    # MLにおいて勾配emaを１次２次相当とするならlossは３次相当以上とみなせる
    def _update_ema(self, state, loss_val):
        ema = state.setdefault('ema', {})
        ema['short'] = 0.3 * loss_val + 0.7 * ema.get('short', loss_val)
        ema['medium'] = 0.05 * loss_val + 0.95 * ema.get('medium', loss_val)
        ema['long'] = 0.01 * loss_val + 0.99 * ema.get('long', loss_val)
        return ema

    # 感情スカラー値生成(EMA差分、滑らかな非線形スカラー、tanh(diff) は ±1.0 で有界性)(内分泌系)
    # scale_base：Loss値とema値の乖離を修正(分母 ema(long)「改善率」共通化/アーキ非依存)
    # 1e-5(デフォルト)／1e-6(感度向上)／1e-4(安定性向上)：分母を０にせず安定(６次近似相当)
    def _compute_scalar(self, ema):
        scale_base_l = max(ema['long'], 1e-5)
        scale_base_m = max(ema['medium'], 1e-5)
        diff_base = ema['long'] - ema['short']
        diff_l = diff_base / scale_base_l
        diff_m = diff_base / scale_base_m
        # longが十分静かなら、常にlongを優先
        if abs(diff_l) < 0.05:
            res_scalar = math.tanh(diff_l)
        # longが静かでない時のみ、mediumの静けさを条件付きで採用
        elif abs(diff_m) * scale_base_m < abs(diff_l) * scale_base_l:
            res_scalar = math.tanh(diff_m)
        else:
            res_scalar = math.tanh(diff_l)
        # scalar と scale_base_m をタプルで返す
        return res_scalar, scale_base_m

    # (重要)全機能は use_shadow=False で成立／通常VRAM負荷は shadow を考慮外(無視できる)
    # emoPulse機構によるダンパー制動はODE縮約を助けるのでshadowは未知のアーキテクチャへの保険(免疫系)
    # Shadow混合比 ３段階構成 タスクに応じ調整可、以下を参考に 開始値・範囲量･変化幅を調整
    # return 開始値 + ((scalar) - 閾値) / 範囲量 * 変化幅 も可能(特殊用途向け)
    def _decide_ratio(self, scalar):
        if not self.use_shadow:
            return 0.0  # 🔸use_shadow = False のとき常に比率を 0 にする
        if abs(scalar) > 0.625:
            return 1.0 - abs(scalar)  # 急変｜強抑制｜tanh 0.73(0.27)
        else:
            return 0.0  # return<0 の場合は leap 専用(書き戻しはしないが履歴更新のみ)

    # 損失取得(損失値 loss_val を数値化、感情判定に使用、存在しないパラメータ(更新不要)はスキップ)
    # closure への対応は loss.backward() と optimizer.step() の間に 
    # optimizer._manual_loss = loss.item() を記述する (通常は ECC に任せる)
    @torch.no_grad()
    def step(self, closure=None):
        loss = torch.enable_grad()(closure)() if closure is not None else None
        loss_val = loss.item() if loss is not None else getattr(self, '_manual_loss', 0.0)

        # EMA更新・スカラー生成(EMA差分からスカラーを生成しスパイク比率等を決定)
        ema = self._update_ema(self.state, loss_val)
        scalar, scale_base_m = self._compute_scalar(ema)
        ratio = self._decide_ratio(scalar)
        trust = math.copysign((1.0 - abs(scalar)), scalar)

        # --- Start emoPulse (完全自動LR生成) ---
        # emoPulse (loss 時系列から制振ダンパーとしてLRを生成)(循環器系)
        # 時間的D推定：loss-LR-lossの閉循環／ML的にこの差分は６次近似相当とみなせる
        self.noise_est = 0.97 * self.noise_est + 0.03 * abs(scalar)
        self.d_est = 0.97 * self.d_est + 0.03 * abs(trust)
        self.c_est = 0.7 * self.c_est + 0.3 * scalar
        noise = max(self.noise_est, 1e-10) # max:1e-12程度(変更後：要アーリーストップ見直し)
        d = self.d_est
        # 瞬間的D推定：(scalar、trust、差分)各時間軸の確度推定(疑念と信頼の綱引き)
        Noise_base = abs(scalar - trust) + 0.1
        d_base = abs(noise - d) + 0.1
        # 異なる時間的確度比率から更新力を導出し２乗で出力最大化(心拍)７次近似相当
        dNR_now_val = (d_base / Noise_base) ** 2
        # 最大値の成長率の増減と履歴化でLRの微調整を担う(非対称性により減衰側を優勢とする)
        if dNR_now_val >= self.dNR_hist and trust >= 0.5:
            # 加速：どんなに dNR が高くても、1.50倍という｢歩幅｣の成長制限
            self.dNR_hist = min(dNR_now_val, self.dNR_hist * 1.50)
        elif -0.5 <= trust <= 0.5:
            # 減速：怪しい時は即座に比率を下げる(確実に信頼できない場合に下げ圧力を溜める)
            self.dNR_hist = dNR_now_val * 0.80
        # 基礎倍率 100^c_est (-1.0 ～ 1.0) max() で 1e-3以下を無視 (100～0.001変動)
        # 0.0：100^0 = 1.0倍, 1.0：100^1 = 100.0倍, -1.0：100^-1 = 0.001倍
        emoChain = self.emoScope * max((100.0 ** self.c_est), 1e-3)
        # emoPulse 最終決定： emoScorp によるユーザー意思の反映と安全値による制限
        emoPulse = float(max(min(self.dNR_hist * (emoChain * self.base_scale),
                                 self.emoScope * self.max_lim), self.min_lim))
        # --- End emoPulse (完全自動LR生成) ---

        for group in self.param_groups:
            beta1, beta2 = group['betas']
            for p in group['params']:
                if p.grad is None:
                    continue

                grad = p.grad
                state = self.state[p]

                # 動的学習率補正により shadow 形成を信頼度で調整(trustは正値化(負にならない))
                # shadow：必要時のみ(スパイクp部分に現在値を最大10%追従させる動的履歴更新)
                # 混合比率：スカラーが閾値を超える場合にのみ計算される(信頼できる感情信号かどうかの選別)
                # 急変時は感情機構による shadow 混合で強く抑制する(急制動による安定性の確保)
                # 機械学習optimizerとしては不要／物理solver的な用途でつかえるかもしれない
                if self.use_shadow :
                    if 'shadow' not in state: # 🔸shadow = False (デフォルト)
                        state['shadow'] = p.clone()
                    if ratio > 0: # 書き戻しと履歴更新(急変時の強い抑制と弱めの履歴更新)
                        p.mul_(1-ratio).add_(state['shadow'], alpha=abs(trust))
                    else: # 書き戻しせず履歴更新のみ：10%×trust
                        leap_ratio = 0.1 * abs(trust)
                        state['shadow'].lerp_(p, leap_ratio)

                # --- Start Gradient Update Logic ---
                # 1次・2次モーメントを使った勾配補正(decoupled weight decay)
                if 'exp_avg' not in state:
                    exp_avg = state.setdefault('exp_avg', torch.zeros_like(p))
                    exp_avg_sq = state.setdefault('exp_avg_sq', torch.zeros_like(p))

                exp_avg = state['exp_avg']
                exp_avg_sq = state['exp_avg_sq']

                exp_avg.mul_(beta1).add_(grad.to(exp_avg.device), alpha=1 - beta1)
                exp_avg_sq.mul_(beta2).addcmul_(grad.to(exp_avg_sq.device), grad.to(exp_avg_sq.device), value=1 - beta2)

                denom = exp_avg_sq.sqrt().add_(group['eps'])

                # FFT版と通常版を統合した分岐(デバイス状態判定へ更新)
                # device 一致の場合のみ sign_() を使い高速化
                if p.device != exp_avg.device:
                    # 節約モード：デバイス間の計算を同じ場所へ統一
                    update = exp_avg.to(p.device)
                else:
                    # 通常モード：同じ場所の場合は負荷軽減
                    update = exp_avg

                if group['weight_decay']:
                    p.mul_(1.0 - group['weight_decay'] * emoPulse)
                p.addcdiv_(update, denom.to(p.device), value=-emoPulse)
                # --- End Gradient Update Logic ---

        # ユーザー指定初期LRを実効値(emoPulse)で可視化する(PyTorch標準)
        for group in self.param_groups:
            group['lr'] = emoPulse

        # 感情機構の穏やかさ"安定状態"を外部伝達する(自動停止ではない)
        # Early Stop：誤判定防止をしないのは点灯頻度で停止準備(予兆)にするため
        self.stop_base = self.d_est - self.noise_est
        if self.stop_base >= 0.3 and scale_base_m <= self.stopcoef:
            self.should_stop = True       # 💡 外部からこれを見て判断可
            if self.notify:               # 💡 収束・安定の「お知らせ」
                print(f"✨[READY TO STOP]✨")
        else:
            self.should_stop = False      # 💡 誤判定などの取り消し

        #print(f"Loss: {loss_val:.4f} | Pulse: {emoPulse:.4e}")

        return

"""
 https://github.com/muooon/EmoSens
 An emotion-driven optimizer that feels loss and navigates accordingly.
 Don't think. Feel. Don't stop. Keep running. Believe in what's beyond.
"""
