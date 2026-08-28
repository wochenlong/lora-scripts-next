# Loss/metric curve reading guide

- Version: `2026-08-29`
- Scope: interpreting training loss curves (TensorBoard `train/loss` or the host unified metrics) with `curve_analyze`.
- Evidence status: project contract + general optimization practice. Labels every judgement as observation vs inference.

## How to read a run

1. **Shape first, numbers second.** A healthy LoRA run shows a fast initial drop, then a gradual descent with small noise. Report trend (descending/flat/rising), plateau start, and spike count — not just the last value.
2. **Spikes** are usually a data or LR event (a bad bucket, a corrupt caption, LR restart). A single early spike that recovers is often harmless; recurring spikes at regular intervals point to the scheduler restart count or a repeated bad sample.
3. **Plateau** = the model has extracted most of the signal from the current data at the current LR. Extending training past a long plateau mostly buys overfitting risk, not quality.
4. **Rising loss** after a descent is a strong overfit/divergence signal — stop earlier, lower LR, or add data/augmentation.
5. **NaN/Inf** is never averaged away: `curve_analyze` retains them. Report the first index; it usually marks a numerics or data fault.

## Mapping to selection

- Prefer a checkpoint at or just before the plateau, not the final epoch, for small sets.
- Always confirm the curve reading with fixed-protocol preview images (same prompt/seed across candidates) — a low loss does not guarantee a usable LoRA.
- State sample coverage: a verdict based on the downsampled curve must say how many raw points it saw.
