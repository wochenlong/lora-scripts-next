---
name: next-trainer-curve-analysis
description: 分析训练 loss/指标曲线（趋势、平台期、尖峰、发散、NaN、欠拟合/过拟合），并基于证据给出继续 / 调整参数 / 早停的建议。Analyze a training loss/metric curve (trend, plateau, spikes, divergence, NaN, under/over-fit) and recommend continue / adjust parameters / early-stop with evidence.
---

# Training curve analysis

Analyze the metric time series, not a single final value.

## Get the series

First locate where the run wrote its outputs: if the user did not state a path,
call the host tool `training_config_current` — the current training parameters
usually contain the model/output directory the user already typed (verify it
exists on disk) — before searching or asking. Then read the metrics / logs from
that location with the native `read` (or `bash`) tools — TensorBoard scalars,
the host unified metrics, or the training log — and pass the series
(step/epoch, train loss, validation loss if present, learning rate, grad norm,
throughput, progress) to the host `curve_analyze` tool for deterministic
trend/statistics computation.

**TensorBoard event files are binary protobuf** (`events.out.tfevents.*`), so do
not `read` them as text. Extract the scalars with a Python one-liner via `bash`
(the project venv has `tensorboard` installed), e.g.:

```bash
python -c "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator; \
ea=EventAccumulator(r'<logging_dir>'); ea.Reload(); tags=ea.Tags()['scalars']; \
[print(t, [(p.step, round(p.value,5)) for p in ea.Scalars(t)]) for t in tags]"
```

Pick the scalar tag that is the training loss (often `train/loss` / `loss` /
`loss_avg`). If several runs exist, choose the run directory matching the run
name in the current training parameters, and say which run you analyzed.

**`curve_analyze` takes the FLAT point sequence — no per-series wrapper.**
`series` is an array of `[step, value]` pairs (or `{"x": step, "y": value}`
objects), one metric per call, named via `metric`:

```text
curve_analyze { "series": [[0, 0.107], [20, 0.097], [40, 0.091], ...], "metric": "loss", "maxPoints": 200 }
```

Do NOT send `{"name": ..., "values": [...]}` or `{"points": [...]}` wrappers —
they fail validation. If you have several metrics (loss, lr, grad norm), call
the tool once per metric and compare the results.

## Analyze

- Descent trend, plateaus, sudden increases, divergence, NaN, abnormal oscillation.
- The relationship between learning-rate changes and loss / grad norm.
- Slope and stability across stages, not just the last point.
- Possible under-fit / over-fit / data-anomaly signals.
- A recommendation with confidence: **continue**, **adjust parameters**, or
  **stop early**.

"Lower loss is better" is **not** the only standard. Without a validation set or
fixed sample images, state clearly that training loss alone cannot judge final
quality.

## Output contract

```text
CurveAnalysis
- series_summary
- anomalies
- stage_assessment
- continue_or_stop_recommendation
- evidence: metric ranges or specific steps the conclusions refer to
- confidence
```

Every metric conclusion must point back to a time interval or a specific step.
