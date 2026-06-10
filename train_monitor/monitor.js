const logBox = document.getElementById("logBox");
const followState = document.getElementById("followState");
const jumpLatest = document.getElementById("jumpLatest");
const togglePreview = document.getElementById("togglePreview");
const logDetails = document.getElementById("logDetails");
const logSummary = document.getElementById("logSummary");
const previewArea = document.getElementById("previewArea");
const lightbox = document.getElementById("previewLightbox");
const lightboxStage = document.getElementById("previewLightboxStage");
const lightboxImage = document.getElementById("previewLightboxImage");
const lightboxMeta = document.getElementById("previewLightboxMeta");
const lightboxClose = document.getElementById("previewLightboxClose");
const lightboxPrev = document.getElementById("previewLightboxPrev");
const lightboxNext = document.getElementById("previewLightboxNext");
let autoFollow = true;
let lastLogText = "";
let lastPreviewKey = "";
let lastResultKey = "";
let previewEnabled = localStorage.getItem("loraMonitorPreviewEnabled") === "1";
let previewItems = [];
const heroEl = document.querySelector(".hero");
const progressTrackEl = document.getElementById("progressTrack");
const progressFillEl = document.getElementById("progressFill");
let chartThemeCache = null;
const lightboxState = {
  open: false,
  index: 0,
  scale: 1,
  minScale: 1,
  maxScale: 4,
  tx: 0,
  ty: 0,
  pointers: new Map(),
  dragging: false,
  dragStartX: 0,
  dragStartY: 0,
  startTx: 0,
  startTy: 0,
  pinchStartDist: 0,
  pinchStartScale: 1
};

function isIdleState(state) {
  return state === "空闲" || state === "GUI 离线";
}

function resolveModelType(status) {
  const raw = (status.model_type || "").trim();
  if (!raw || raw === "未知类型" || raw === "未知") {
    return isIdleState(status.state || "") ? "" : raw;
  }
  return raw;
}

function heroTitleText(status) {
  const state = status.state || "-";
  const model = resolveModelType(status);
  if (isIdleState(state)) return "当前空闲";
  if (state === "训练中") return (model || "训练任务") + " · 训练中";
  if (state === "已结束") return (model || "训练任务") + " · 已结束";
  return (model || "训练任务") + " " + state;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, function(ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function distance(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function updateLightboxTransform() {
  if (!lightboxImage) return;
  lightboxImage.style.transform = "translate(" + lightboxState.tx + "px," + lightboxState.ty + "px) scale(" + lightboxState.scale + ")";
}

function resetLightboxTransform() {
  lightboxState.scale = 1;
  lightboxState.tx = 0;
  lightboxState.ty = 0;
  lightboxState.dragging = false;
  lightboxState.pinchStartDist = 0;
  lightboxState.pinchStartScale = 1;
  lightboxState.pointers.clear();
  updateLightboxTransform();
}

function canNavigateLightbox() {
  return previewItems.length > 1;
}

function updateLightboxNav() {
  const enabled = canNavigateLightbox();
  if (lightboxPrev) lightboxPrev.disabled = !enabled;
  if (lightboxNext) lightboxNext.disabled = !enabled;
}

function renderLightboxFrame() {
  const item = previewItems[lightboxState.index];
  if (!item || !lightboxImage || !lightboxMeta) return;
  lightboxImage.src = item.url;
  lightboxImage.alt = item.name || "训练预览图";
  const role = item.role ? "[" + item.role + "] " : "";
  lightboxMeta.textContent = role + (item.name || "-") + " · " + (lightboxState.index + 1) + "/" + previewItems.length;
  updateLightboxNav();
  resetLightboxTransform();
}

function openLightbox(index) {
  if (!previewItems.length || !lightbox) return;
  lightboxState.index = clamp(index, 0, previewItems.length - 1);
  lightboxState.open = true;
  lightbox.classList.remove("hidden");
  lightbox.setAttribute("aria-hidden", "false");
  document.body.classList.add("lightbox-open");
  renderLightboxFrame();
}

function closeLightbox() {
  if (!lightbox || !lightboxState.open) return;
  lightboxState.open = false;
  lightbox.classList.add("hidden");
  lightbox.setAttribute("aria-hidden", "true");
  document.body.classList.remove("lightbox-open");
  if (lightboxImage) {
    lightboxImage.removeAttribute("src");
  }
  resetLightboxTransform();
}

function stepLightbox(delta) {
  if (!previewItems.length) return;
  lightboxState.index = (lightboxState.index + delta + previewItems.length) % previewItems.length;
  renderLightboxFrame();
}

function zoomLightbox(factor, centerX, centerY) {
  const prevScale = lightboxState.scale;
  const nextScale = clamp(prevScale * factor, lightboxState.minScale, lightboxState.maxScale);
  if (Math.abs(nextScale - prevScale) < 1e-4) return;
  if (!lightboxStage) return;
  const rect = lightboxStage.getBoundingClientRect();
  const cx = centerX - rect.left - rect.width / 2;
  const cy = centerY - rect.top - rect.height / 2;
  lightboxState.tx = (lightboxState.tx - cx) * (nextScale / prevScale) + cx;
  lightboxState.ty = (lightboxState.ty - cy) * (nextScale / prevScale) + cy;
  lightboxState.scale = nextScale;
  if (nextScale <= 1.0001) {
    lightboxState.tx = 0;
    lightboxState.ty = 0;
  }
  updateLightboxTransform();
}

function bindLightboxEvents() {
  if (!lightbox || !lightboxStage || !lightboxImage) return;
  if (bindLightboxEvents._bound) return;
  bindLightboxEvents._bound = true;

  previewArea.addEventListener("click", function(event) {
    const card = event.target.closest(".preview-card");
    if (!card || !previewEnabled) return;
    const idx = Number(card.getAttribute("data-preview-index"));
    if (Number.isFinite(idx)) openLightbox(idx);
  });
  previewArea.addEventListener("keydown", function(event) {
    const card = event.target.closest(".preview-card");
    if (!card || !previewEnabled) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    const idx = Number(card.getAttribute("data-preview-index"));
    if (Number.isFinite(idx)) openLightbox(idx);
  });

  lightbox.addEventListener("click", function(event) {
    if (event.target && event.target.getAttribute("data-lightbox-close") === "1") closeLightbox();
  });
  lightboxClose.addEventListener("click", closeLightbox);
  lightboxPrev.addEventListener("click", function() { stepLightbox(-1); });
  lightboxNext.addEventListener("click", function() { stepLightbox(1); });

  document.addEventListener("keydown", function(event) {
    if (!lightboxState.open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeLightbox();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepLightbox(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      stepLightbox(1);
    }
  });

  lightboxStage.addEventListener("wheel", function(event) {
    if (!lightboxState.open) return;
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.1 : 0.9;
    zoomLightbox(factor, event.clientX, event.clientY);
  }, { passive: false });

  lightboxStage.addEventListener("dblclick", function(event) {
    if (!lightboxState.open) return;
    event.preventDefault();
    if (lightboxState.scale > 1.01) resetLightboxTransform();
    else zoomLightbox(2, event.clientX, event.clientY);
  });

  lightboxImage.addEventListener("pointerdown", function(event) {
    if (!lightboxState.open) return;
    lightboxImage.setPointerCapture(event.pointerId);
    lightboxState.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (lightboxState.pointers.size === 1) {
      lightboxState.dragging = true;
      lightboxState.dragStartX = event.clientX;
      lightboxState.dragStartY = event.clientY;
      lightboxState.startTx = lightboxState.tx;
      lightboxState.startTy = lightboxState.ty;
    } else if (lightboxState.pointers.size === 2) {
      const arr = Array.from(lightboxState.pointers.values());
      lightboxState.dragging = false;
      lightboxState.pinchStartDist = distance(arr[0], arr[1]);
      lightboxState.pinchStartScale = lightboxState.scale;
    }
  });

  lightboxImage.addEventListener("pointermove", function(event) {
    if (!lightboxState.open || !lightboxState.pointers.has(event.pointerId)) return;
    lightboxState.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (lightboxState.pointers.size >= 2) {
      const arr = Array.from(lightboxState.pointers.values());
      const dist = distance(arr[0], arr[1]);
      if (lightboxState.pinchStartDist > 0) {
        const factor = dist / lightboxState.pinchStartDist;
        const centerX = (arr[0].x + arr[1].x) / 2;
        const centerY = (arr[0].y + arr[1].y) / 2;
        const targetScale = clamp(lightboxState.pinchStartScale * factor, lightboxState.minScale, lightboxState.maxScale);
        const zoomFactor = targetScale / lightboxState.scale;
        zoomLightbox(zoomFactor, centerX, centerY);
      }
      return;
    }

    if (!lightboxState.dragging) return;
    if (lightboxState.scale <= 1.0001) return;
    lightboxState.tx = lightboxState.startTx + (event.clientX - lightboxState.dragStartX);
    lightboxState.ty = lightboxState.startTy + (event.clientY - lightboxState.dragStartY);
    updateLightboxTransform();
  });

  function releasePointer(event) {
    lightboxState.pointers.delete(event.pointerId);
    if (lightboxState.pointers.size === 0) {
      lightboxState.dragging = false;
      lightboxState.pinchStartDist = 0;
      lightboxState.pinchStartScale = lightboxState.scale;
      if (lightboxState.scale <= 1.0001) {
        resetLightboxTransform();
      }
    } else if (lightboxState.pointers.size === 1) {
      const p = Array.from(lightboxState.pointers.values())[0];
      lightboxState.dragging = true;
      lightboxState.dragStartX = p.x;
      lightboxState.dragStartY = p.y;
      lightboxState.startTx = lightboxState.tx;
      lightboxState.startTy = lightboxState.ty;
      lightboxState.pinchStartDist = 0;
    }
  }

  lightboxImage.addEventListener("pointerup", releasePointer);
  lightboxImage.addEventListener("pointercancel", releasePointer);
}

function isNearBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 64;
}

function scrollToLatest() {
  logBox.scrollTop = logBox.scrollHeight;
}

function setAutoFollow(value) {
  autoFollow = value;
  followState.textContent = autoFollow ? "自动跟随最新" : "已暂停，正在查看历史日志";
  followState.classList.toggle("paused", !autoFollow);
  jumpLatest.classList.toggle("hidden", autoFollow);
}

logBox.addEventListener("scroll", function() {
  setAutoFollow(isNearBottom(logBox));
});

jumpLatest.addEventListener("click", function() {
  setAutoFollow(true);
  scrollToLatest();
});

togglePreview.addEventListener("click", function() {
  previewEnabled = !previewEnabled;
  localStorage.setItem("loraMonitorPreviewEnabled", previewEnabled ? "1" : "0");
  lastPreviewKey = "";
  renderPreviewToggle();
  pollStatus();
});

function renderTrainParams(status) {
  const el = document.getElementById("trainParams");
  const gpu = status.gpu_info;
  const params = status.train_params || [];
  const metrics = status.metrics || {};

  var gpuHtml = '';
  if (gpu) {
    const vramPct = gpu.vram_total_mb > 0 ? Math.round(gpu.vram_used_mb * 100 / gpu.vram_total_mb) : 0;
    const vramGB = (gpu.vram_used_mb / 1024).toFixed(1);
    const vramTotalGB = (gpu.vram_total_mb / 1024).toFixed(1);
    const loadPct = gpu.gpu_load || 0;
    const tempColor = (gpu.temperature || 0) >= 80 ? 'var(--err)' : (gpu.temperature || 0) >= 65 ? 'var(--warn)' : 'var(--ok)';
    const tempText = gpu.temperature != null ? gpu.temperature + '°C' : '-';
    const powerText = gpu.power_w != null ? gpu.power_w + 'W' + (gpu.power_limit_w ? ' / ' + gpu.power_limit_w + 'W' : '') : '';
    gpuHtml = '<div class="param-card"><div class="gpu-panel">'
      + '<div class="gpu-header"><span class="gpu-name">' + escapeHtml(gpu.name) + '</span>'
      + '<span class="gpu-temp" style="color:' + tempColor + '">' + tempText + '</span></div>'
      + '<div class="gpu-bars">'
      + '<div class="gpu-bar-row"><div class="gpu-bar-label"><span>GPU Load</span><strong>' + loadPct + '%</strong></div>'
      + '<div class="gpu-bar-track"><div class="gpu-bar-fill load" style="width:' + loadPct + '%"></div></div></div>'
      + '<div class="gpu-bar-row"><div class="gpu-bar-label"><span>VRAM</span><strong>' + vramGB + ' / ' + vramTotalGB + ' GB</strong></div>'
      + '<div class="gpu-bar-track"><div class="gpu-bar-fill vram" style="width:' + vramPct + '%"></div></div></div>'
      + '</div>'
      + (powerText ? '<div class="gpu-power">⚡ ' + powerText + '</div>' : '')
      + '</div></div>';
  } else {
    gpuHtml = '<div class="param-card"><div class="gpu-panel"><span class="muted">GPU 信息不可用</span></div></div>';
  }

  var stepsHero = params.find(function(p) { return p.label === '总步数' || p.label === '设定总步数' || p.label === '每 Epoch'; });
  var stepsHtml = '';
  if (stepsHero) {
    var parts = escapeHtml(stepsHero.value).match(/^(\d+)(.*)/);
    var mainVal = parts ? parts[1] : escapeHtml(stepsHero.value);
    var detail = parts && parts[2] ? parts[2].replace(/^[（(]\s*/, '').replace(/\s*[)）]$/, '') : '';
    stepsHtml = '<div class="param-card"><div class="steps-hero">'
      + '<div class="sh-label">' + escapeHtml(stepsHero.label) + '</div>'
      + '<div class="sh-value">' + mainVal + '</div>'
      + (detail ? '<div class="sh-detail">' + detail + '</div>' : '')
      + '</div></div>';
  } else {
    stepsHtml = '<div class="param-card"><div class="steps-hero"><div class="sh-label">总步数</div><div class="sh-value">-</div></div></div>';
  }

  var summaryItems = [];
  function addParam(label, keys) {
    for (var i = 0; i < keys.length; i++) {
      var p = params.find(function(item) { return item.label === keys[i]; });
      if (p) { summaryItems.push({label: label, value: p.value}); return; }
    }
  }
  var lr = metrics.lr;
  if (!lr) {
    var lrParam = params.find(function(p) { return p.label === '学习率' || p.label === 'UNet LR'; });
    if (lrParam) lr = lrParam.value;
  }
  if (lr) summaryItems.push({label: '学习率', value: lr});
  addParam('优化器', ['优化器']);
  addParam('调度器', ['调度器']);
  addParam('Rank', ['Rank (dim)']);
  addParam('Alpha', ['Alpha']);
  addParam('精度', ['精度']);
  addParam('分辨率', ['分辨率']);
  addParam('总 Epochs', ['总 Epochs']);
  addParam('Noise Offset', ['Noise Offset']);

  var paramHtml = '';
  if (summaryItems.length > 0) {
    paramHtml = '<div class="param-card"><div class="param-summary">'
      + '<div class="param-summary-title">训练参数</div>'
      + '<div class="param-summary-items">'
      + summaryItems.map(function(item) {
          return '<div class="ps-item"><div class="ps-label">' + escapeHtml(item.label) + '</div><div class="ps-value" title="' + escapeHtml(item.value) + '">' + escapeHtml(item.value) + '</div></div>';
        }).join('')
      + '</div></div></div>';
  } else {
    paramHtml = '<div class="param-card"><div class="param-summary"><span class="muted" style="font-size:12px;">等待训练启动后显示参数。</span></div></div>';
  }

  el.innerHTML = '<div class="param-row">' + gpuHtml + stepsHtml + paramHtml + '</div>';
}

function progressText(metrics) {
  if (!metrics || metrics.step === undefined) return "-";
  let text = String(metrics.step) + "/" + String(metrics.total_steps ?? "-");
  if (metrics.percent !== undefined) text += " (" + String(metrics.percent) + "%)";
  return text;
}

function renderCards(status) {
  const metrics = status.metrics || {};
  const modelLabel = resolveModelType(status) || "—";
  const cards = [
    ["模型类型", modelLabel],
    ["状态", status.state || "-"],
    ["进度", progressText(metrics)],
    ["Epoch", metrics.epoch || "-"],
    ["耗时", metrics.duration || metrics.elapsed || "-"],
    ["剩余", status.state === "训练中" ? (metrics.eta || "-") : "-"],
    ["Loss", metrics.loss || "-"],
  ];
  const isTraining = status.state === "训练中";
  const accentLabels = { "状态": true, "进度": true, "Loss": true };
  document.getElementById("cards").innerHTML = cards.map(function(card) {
    const accent = isTraining && accentLabels[card[0]] ? " card--accent" : "";
    const valueClass = card[0] === "状态" && isTraining ? " value value--live" : " value";
    return '<div class="card' + accent + '"><div class="label">' + escapeHtml(card[0]) + '</div><div class="' + valueClass.trim() + '">' + escapeHtml(card[1] || "-") + '</div></div>';
  }).join("");
}

function renderHero(status) {
  const metrics = status.metrics || {};
  const modelType = resolveModelType(status) || "训练任务";
  const state = status.state || "-";
  const pct = Number(metrics.percent || 0);
  const hasPct = Number.isFinite(pct) && pct > 0;
  const error = status.error || status.log_error || metrics.has_error;
  const guiWarning = status.gui_warning || "";
  const attention = metrics.needs_attention || metrics.progress_stalled;
  const isTraining = state === "训练中" && !error && !attention;
  let title = heroTitleText(status);
  let copy = "正在等待训练状态。";
  const lossText = metrics.loss ? "Loss " + metrics.loss : "";
  const trendText = metrics.loss_trend ? "，" + metrics.loss_trend : "";

  if (error) {
    title = "训练需要关注";
    copy = "检测到强错误信号，并结合任务状态判断训练可能已异常退出。";
  } else if (attention) {
    title = "训练需要关注";
    copy = metrics.progress_stalled
      ? "训练 step 已长时间未增长，请观察显存和日志。"
      : "日志中出现强错误信号，但训练仍在推进，先不自动展开日志。";
  } else if (state === "训练中") {
    copy = (resolveModelType(status) || "训练任务") + " 进行中" +
      (metrics.elapsed ? "，已训练 " + metrics.elapsed : "") +
      (lossText ? "，" + lossText + trendText : "") +
      (metrics.eta ? "，预计还需 " + metrics.eta + "。" : "。");
  } else if (state === "已结束") {
    copy = (resolveModelType(status) || "训练任务") + " 已完成" +
      (metrics.duration ? "，总耗时 " + metrics.duration : "") +
      (lossText ? "，" + lossText + trendText : "") + "，最新模型已保存到输出目录。";
  } else if (isIdleState(state)) {
    copy = state === "GUI 离线"
      ? (guiWarning || "主 GUI 未连接，无法获取任务列表；GPU、训练参数与 TensorBoard Loss 仍可从本页读取。")
      : "当前没有进行中的训练；启动训练后将显示模型类型与实时进度。";
  }

  if (heroEl) {
    heroEl.classList.remove("hero--warn", "hero--error", "hero--training");
    if (error) heroEl.classList.add("hero--error");
    else if (attention) heroEl.classList.add("hero--warn");
    else if (isTraining) heroEl.classList.add("hero--training");
  }
  document.body.classList.toggle("monitor-training", isTraining);
  document.getElementById("heroTitle").textContent = title;
  document.getElementById("heroCopy").textContent = copy;
  document.getElementById("heroPercent").textContent = hasPct ? pct.toFixed(pct % 1 === 0 ? 0 : 1) + "%" : (isTraining ? "0%" : "-");
  const clampedPct = Math.max(0, Math.min(100, pct || 0));
  if (progressFillEl) {
    progressFillEl.style.width = clampedPct + "%";
    progressFillEl.classList.toggle("progress-fill--active", isTraining && clampedPct > 0);
  }
  if (progressTrackEl) progressTrackEl.classList.toggle("progress-track--hot", isTraining && clampedPct >= 90);
  renderSamplingProgress(metrics.sampling, status);
}

function renderSamplingProgress(sampling, status) {
  const text = document.getElementById("sampleProgressText");
  const fill = document.getElementById("sampleProgressFill");
  if (!sampling || !sampling.active) {
    fill.style.width = sampling && sampling.percent >= 100 ? "100%" : "0%";
    if (sampling && sampling.percent >= 100) {
      const atStep = sampling.train_step ? "（训练 step " + sampling.train_step + "）" : "";
      text.textContent = "预览图生成进度：最近一次采样已完成" + atStep;
    } else if (status && status.state === "训练中") {
      text.textContent = "预览图生成进度：等待下一次采样";
    } else {
      text.textContent = "预览图生成进度：暂无采样任务";
    }
    return;
  }
  const pct = Number(sampling.percent || 0);
  fill.style.width = Math.max(0, Math.min(100, pct)) + "%";
  const atStep = sampling.train_step ? "（训练 step " + sampling.train_step + "）" : "";
  text.textContent = "预览图生成中" + atStep + "：" + sampling.step + "/" + sampling.total_steps + "（" + pct + "%）" + (sampling.eta ? "，预计 " + sampling.eta : "");
}

function fmtLoss(v) {
  if (v === null || v === undefined || v === "") return "-";
  const n = Number(v);
  if (!Number.isFinite(n)) return "-";
  const abs = Math.abs(n);
  if (abs >= 1) return n.toFixed(3);
  if (abs >= 0.01) return n.toFixed(4);
  return n.toExponential(2);
}

function getChartTheme() {
  if (chartThemeCache) return chartThemeCache;
  const style = getComputedStyle(document.documentElement);
  const pick = function(name, fallback) {
    const value = style.getPropertyValue(name).trim();
    return value || fallback;
  };
  chartThemeCache = {
    tooltipBg: "rgba(10,14,26,0.96)",
    border: pick("--line", "#243049"),
    text: pick("--text", "#e8eef7"),
    axis: pick("--color-chart-axis", "#9aa7bd"),
    grid: pick("--color-chart-grid", "#2a344d"),
    line: pick("--color-chart-line", "#16bac5"),
    area: pick("--color-chart-area", "rgba(22,186,197,0.10)")
  };
  return chartThemeCache;
}

var tbLossCharts = {};
var tbLossLayoutKey = "";
var tbLossRange = "20p";
var tbLossManualZoom = false;
var latestStatus = null;
window.addEventListener("resize", function() {
  Object.keys(tbLossCharts).forEach(function(key) {
    tbLossCharts[key].resize();
  });
});

document.getElementById("tbLossControls").addEventListener("click", function(event) {
  const button = event.target.closest("button[data-range]");
  if (!button) return;
  tbLossRange = button.dataset.range === "latest" ? "20p" : button.dataset.range;
  tbLossManualZoom = false;
  Array.from(this.querySelectorAll("button")).forEach(function(btn) {
    btn.classList.toggle("active", btn.dataset.range === tbLossRange || (button.dataset.range === "latest" && btn.dataset.range === "20p"));
  });
  if (latestStatus) renderLossChart(latestStatus.metrics || {}, latestStatus);
});

function buildLogLossSeries(metrics) {
  const raw = (metrics && metrics.loss_points) || [];
  if (!raw.length) return [];
  const points = raw.map(function(point) {
    return { step: Number(point.step) || 0, value: Number(point.loss) };
  }).filter(function(point) {
    return Number.isFinite(point.step) && Number.isFinite(point.value);
  });
  if (!points.length) return [];
  const values = points.map(function(point) { return point.value; });
  return [{
    tag: "avr_loss (log)",
    name: "avr_loss from training log",
    points: points,
    latest: values[values.length - 1],
    min: Math.min.apply(null, values),
    max: Math.max.apply(null, values),
    run: "stdout parse"
  }];
}

function pickPrimaryLossSeries(series) {
  const preferred = ["loss/average", "loss/current", "loss", "loss/epoch_average", "loss/epoch"];
  for (let i = 0; i < preferred.length; i += 1) {
    const match = series.find(function(item) { return item.tag === preferred[i]; });
    if (match) return match;
  }
  return series[0];
}

function renderLossChart(metrics, status) {
  latestStatus = status;
  const summary = document.getElementById("lossSummary");
  const area = document.getElementById("tensorboardLossArea");
  let series = (status && status.tensorboard_loss) || [];
  let usingLogFallback = false;
  if (!series.length) {
    series = buildLogLossSeries(metrics);
    usingLogFallback = series.length > 0;
  }
  const fallbackLoss = metrics && metrics.loss ? metrics.loss : "-";

  if (!series.length) {
    Object.keys(tbLossCharts).forEach(function(key) {
      tbLossCharts[key].dispose();
      delete tbLossCharts[key];
    });
    tbLossLayoutKey = "";
    summary.innerHTML = '<span>当前 Loss：<strong>' + escapeHtml(fallbackLoss) + '</strong></span>' +
      '<span class="muted">等待 TensorBoard event 写入 Loss scalar</span>';
    area.className = "tb-loss-empty";
    area.innerHTML = "等待 TensorBoard Loss 数据。训练刚启动时可能需要几十秒。";
    return;
  }

  const latestAverage = pickPrimaryLossSeries(series);
  summary.innerHTML = '<span>' + (usingLogFallback ? "日志 Loss" : "TensorBoard Loss") + '：<strong>' +
    escapeHtml(fmtLoss(latestAverage.latest)) + '</strong></span>' +
    '<span class="pill">' + escapeHtml(latestAverage.tag) + '</span>' +
    '<span class="muted">' + (usingLogFallback
      ? "由训练日志解析的 avr_loss 曲线"
      : "真实 scalar 曲线，和 TensorBoard 同源") + '</span>';

  area.className = "tb-loss-grid";
  const hasLearningRate = series.some(function(item) { return /^lr\//.test(item.tag); });
  const displaySeries = hasLearningRate ? series : series.concat([{
    tag: "lr",
    name: "learning rate",
    points: [],
    latest: null,
    min: null,
    run: "",
    missing: true
  }]);
  const layoutKey = displaySeries.map(function(item) { return item.tag + (item.missing ? ":missing" : ""); }).join("|");
  if (layoutKey !== tbLossLayoutKey) {
    Object.keys(tbLossCharts).forEach(function(key) {
      tbLossCharts[key].dispose();
      delete tbLossCharts[key];
    });
    area.innerHTML = displaySeries.map(function(item, idx) {
      return '<div class="tb-loss-card">' +
        '<div class="tb-loss-head">' +
        '<div><div class="tb-loss-title">' + escapeHtml(item.tag) + '</div>' +
        '<div class="muted">' + escapeHtml(item.run || "logs") + '</div></div>' +
        '<div class="tb-loss-meta" id="tbLossMeta' + idx + '">latest ' + escapeHtml(fmtLoss(item.latest)) +
        '<br>min ' + escapeHtml(fmtLoss(item.min)) + '</div>' +
        '</div>' +
        (item.missing
          ? '<div class="tb-loss-missing">暂无 learning rate scalar</div>'
          : '<div class="tb-loss-chart" id="tbLossChart' + idx + '"></div>') +
        '</div>';
    }).join("");
    tbLossLayoutKey = layoutKey;
  }

  displaySeries.forEach(function(item, idx) {
    const meta = document.getElementById("tbLossMeta" + idx);
    if (meta) meta.innerHTML = "latest " + escapeHtml(fmtLoss(item.latest)) + "<br>min " + escapeHtml(fmtLoss(item.min));
    if (item.missing) return;
    const chartDom = document.getElementById("tbLossChart" + idx);
    if (!chartDom) return;
    const chart = tbLossCharts[item.tag] || echarts.init(chartDom, null, { renderer: "canvas" });
    tbLossCharts[item.tag] = chart;
    const points = item.points || [];
    const data = points.map(function(point) {
      return [Number(point.step) || 0, Number(point.value)];
    });
    const dataZoom = [{
      type: "inside",
      xAxisIndex: 0,
      filterMode: "none",
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false
    }];
    if (!tbLossManualZoom && tbLossRange !== "all" && data.length) {
      const latestStep = data[data.length - 1][0];
      const firstStep = data[0][0];
      const span = Math.max(1, latestStep - firstStep + 1);
      const percent = tbLossRange.endsWith("p") ? Number(tbLossRange.slice(0, -1)) : 20;
      const range = Math.max(1, Math.round(span * Math.max(1, Math.min(100, percent)) / 100));
      dataZoom[0].startValue = Math.max(firstStep, latestStep - range + 1);
      dataZoom[0].endValue = latestStep;
    }
    if (!chart.__tbLossZoomBound) {
      chart.on("dataZoom", function() {
        tbLossManualZoom = true;
      });
      chart.__tbLossZoomBound = true;
    }
    const theme = getChartTheme();
    const option = {
      backgroundColor: "transparent",
      animation: false,
      grid: { left: 46, right: 18, top: 12, bottom: 24, containLabel: false },
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg,
        borderColor: theme.border,
        textStyle: { color: theme.text, fontSize: 12 },
        formatter: function(params) {
          if (!params || !params.length) return "";
          var value = params[0].value || [];
          return '<strong>step ' + escapeHtml(value[0]) + '</strong><br>' +
            escapeHtml(item.tag) + ': <strong>' + escapeHtml(fmtLoss(value[1])) + '</strong>';
        }
      },
      xAxis: {
        type: "value",
        axisLine: { lineStyle: { color: theme.axis, opacity: 0.35 } },
        axisTick: { show: false },
        axisLabel: { color: theme.axis, fontSize: 10 },
        splitLine: { lineStyle: { color: theme.grid, opacity: 0.55 } }
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: theme.axis, fontSize: 10, formatter: function(v) { return fmtLoss(v); } },
        splitLine: { lineStyle: { color: theme.grid, opacity: 0.55 } }
      },
      dataZoom: dataZoom,
      series: [{
        name: item.tag,
        type: "line",
        data: data,
        showSymbol: false,
        symbolSize: 2,
        sampling: "lttb",
        lineStyle: { color: theme.line, width: 1.5 },
        itemStyle: { color: theme.line },
        areaStyle: { color: theme.area }
      }]
    };
    chart.setOption(option, { replaceMerge: ["dataZoom", "series"] });
  });
}

function filterModelFiles(files) {
  return (files || []).filter(function(item) {
    return /\.(safetensors|ckpt|pt)$/i.test(item.name || "");
  });
}

function formatRelativeMtime(item) {
  const ts = Number(item.mtime_ts);
  if (!Number.isFinite(ts) || ts <= 0) return item.mtime || "-";
  const diffSec = Math.max(0, Date.now() / 1000 - ts);
  if (diffSec < 60) return "刚刚";
  if (diffSec < 3600) return Math.floor(diffSec / 60) + " 分钟前";
  if (diffSec < 86400) return Math.floor(diffSec / 3600) + " 小时前";
  if (diffSec < 86400 * 2) return "昨天 " + (item.mtime || "").split(" ")[1] || "";
  if (diffSec < 86400 * 7) return Math.floor(diffSec / 86400) + " 天前";
  return item.mtime || "-";
}

function resultOutputBadge(status, latest) {
  const state = status.state || "";
  const ageSec = latest && Number.isFinite(Number(latest.mtime_ts))
    ? Math.max(0, Date.now() / 1000 - Number(latest.mtime_ts))
    : 999999;
  if (state === "训练中" || state === "已结束") {
    return { cls: "result-badge result-badge--fresh", text: "最新输出" };
  }
  if (isIdleState(state) || ageSec > 6 * 3600) {
    return { cls: "result-badge result-badge--history", text: "历史输出" };
  }
  return { cls: "result-badge result-badge--fresh", text: "最新输出" };
}

function copyResultText(text, button) {
  const value = String(text || "");
  if (!value) return;
  const done = function() {
    const original = button.textContent;
    button.textContent = "已复制";
    button.classList.add("btn-ghost--done");
    setTimeout(function() {
      button.textContent = original;
      button.classList.remove("btn-ghost--done");
    }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(done).catch(function() {
      window.prompt("复制以下内容：", value);
    });
    return;
  }
  window.prompt("复制以下内容：", value);
}

function bindResultActions(root) {
  if (!root) return;
  root.querySelectorAll("[data-copy]").forEach(function(button) {
    if (button.__copyBound) return;
    button.__copyBound = true;
    button.addEventListener("click", function() {
      copyResultText(button.getAttribute("data-copy"), button);
    });
  });
}

function renderResultRowActions(item) {
  return '<button type="button" class="btn-ghost" data-copy="' + escapeHtml(item.path) + '">复制</button>';
}

function renderResultOtherWorks(other) {
  if (!other.length) return "";
  return '<details class="result-other-works">' +
    '<summary>其它作品目录（' + other.length + '）</summary>' +
    '<div class="result-table-wrap">' +
    '<table class="result-table">' +
    '<thead><tr><th>文件名</th><th>目录</th><th>大小</th><th>时间</th><th></th></tr></thead>' +
    '<tbody>' +
    other.map(function(item) {
      return '<tr>' +
        '<td class="result-table__name" title="' + escapeHtml(item.name) + '"><code>' + escapeHtml(item.name) + '</code></td>' +
        '<td class="result-table__folder" title="' + escapeHtml(item.folder || "") + '">' + escapeHtml(item.folder || "-") + '</td>' +
        '<td>' + escapeHtml(item.size) + '</td>' +
        '<td title="' + escapeHtml(item.mtime || "") + '">' + escapeHtml(formatRelativeMtime(item)) + '</td>' +
        '<td class="result-table__actions">' + renderResultRowActions(item) + '</td>' +
        '</tr>';
    }).join("") +
    '</tbody></table></div></details>';
}

function renderResult(status) {
  const primary = filterModelFiles(status.outputs_primary || []);
  const fallback = filterModelFiles(status.outputs || []);
  const modelFiles = primary.length ? primary : fallback;
  const scope = status.output_scope || "";
  const otherWorks = filterModelFiles(status.outputs_other || []);

  if (modelFiles.length === 0) {
    return '<div class="result-empty muted">暂无模型输出。训练完成后会在这里显示模型保存位置。</div>';
  }

  const latest = modelFiles[0];
  const badge = resultOutputBadge(status, latest);
  const ext = latest.ext || (latest.name.match(/\.[^.]+$/) || [""])[0];
  const folderLabel = latest.folder || latest.rel_path || scope || "";

  let html = "";
  if (scope && primary.length) {
    html += '<div class="result-scope">当前训练目录：<code>' + escapeHtml(scope) + '</code></div>';
  } else if (!primary.length && fallback.length) {
    html += '<div class="result-scope result-scope--fallback">未定位到当前训练 output_dir，以下为 output 根目录最近模型。</div>';
  }

  html += '<div class="result-latest">' +
    '<span class="' + badge.cls + '">' + escapeHtml(badge.text) + '</span>' +
    '<div class="result-latest__body">' +
    '<div class="result-latest__main">' +
    (ext ? '<span class="result-ext">' + escapeHtml(ext) + '</span>' : "") +
    '<div class="result-latest__text">' +
    '<div class="result-name">' + escapeHtml(latest.name) + '</div>' +
    '<div class="result-meta">' + escapeHtml(latest.size) + ' · ' + escapeHtml(formatRelativeMtime(latest)) + '</div>' +
    (folderLabel ? '<div class="result-folder" title="' + escapeHtml(folderLabel) + '">' + escapeHtml(folderLabel) + '</div>' : "") +
    '</div></div>' +
    '<div class="result-actions">' +
    '<button type="button" class="btn-ghost" data-copy="' + escapeHtml(latest.path) + '">复制路径</button>' +
    '<button type="button" class="btn-ghost" data-copy="' + escapeHtml(latest.name) + '">复制文件名</button>' +
    '</div></div>' +
    '<div class="result-path-line" title="' + escapeHtml(latest.path) + '">' + escapeHtml(latest.path) + '</div>' +
    '</div>';

  html += renderResultOtherWorks(otherWorks);
  return html;
}

function renderResultDuration(status, metrics) {
  const el = document.getElementById("resultDuration");
  if (!el) return;
  const parts = [];
  const duration = metrics && (metrics.duration || metrics.elapsed);
  if (duration) parts.push("本次训练耗时：" + duration);
  const primary = (status.outputs_primary || []).length;
  if (primary > 0 && status.output_scope) {
    parts.push("目录内 " + primary + " 个模型文件");
  }
  el.textContent = parts.join(" · ");
}

function renderPreviewToggle() {
  togglePreview.classList.toggle("preview-toggle--on", previewEnabled);
  togglePreview.setAttribute("aria-pressed", previewEnabled ? "true" : "false");
  const label = togglePreview.querySelector(".preview-toggle__text");
  if (label) label.textContent = previewEnabled ? "预览已开启" : "开启预览";
  if (!previewEnabled) {
    document.getElementById("previewArea").innerHTML = '<div class="preview-hidden"><strong>预览图未加载</strong>点击右侧"开启预览图"后，当前浏览器才会加载训练图片；关闭时不会请求图片，适合公开端口截图。</div>';
    lastPreviewKey = "";
    previewItems = [];
    closeLightbox();
  }
}

function previewProgressParts(item, metrics) {
  const epoch = Number(item.epoch);
  const maxEpoch = Number(item.max_epoch);
  const totalSteps = Number(metrics && metrics.total_steps);
  if (Number.isFinite(epoch)) {
    let stepText = epoch === 0 ? "Step 0" : "";
    if (Number.isFinite(maxEpoch) && maxEpoch > 0 && Number.isFinite(totalSteps) && totalSteps > 0) {
      const step = Math.round(totalSteps * epoch / maxEpoch);
      stepText = "Step " + step;
    }
    return { step: stepText || "Step -", epoch: "Epoch " + epoch };
  }
  return { step: item.role || "预览图", epoch: "Epoch -" };
}

function renderPreviews(previews, metrics) {
  const area = previewArea;
  if (!previewEnabled) {
    renderPreviewToggle();
    return;
  }
  previewItems = previews || [];
  if (lightboxState.open && lightboxState.index >= previewItems.length) {
    lightboxState.index = Math.max(0, previewItems.length - 1);
    if (previewItems.length) renderLightboxFrame();
    else closeLightbox();
  }
  if (!previews || previews.length === 0) {
    if (lastPreviewKey !== "__empty__") {
      area.innerHTML = '<div class="muted">还没有训练预览图。通常会在第一次采样后出现在这里。</div>';
      lastPreviewKey = "__empty__";
    }
    return;
  }
  const previewKey = previews.map(function(item) {
    return item.url + "|" + item.mtime + "|" + item.size;
  }).join("||");
  if (previewKey === lastPreviewKey) return;
  lastPreviewKey = previewKey;
  const count = previews.length;
  const gridClass = "preview-grid preview-grid--count-" + Math.min(count, 3);
  area.innerHTML = '<div class="' + gridClass + '">' + previews.map(function(item, idx) {
    const progress = previewProgressParts(item, metrics || {});
    return '<div class="preview-card" data-preview-index="' + idx + '" role="button" tabindex="0" aria-label="放大查看 ' + escapeHtml(item.name) + '">' +
      (item.role ? '<span class="preview-role">' + escapeHtml(item.role) + '</span>' : '') +
      '<div class="preview-media"><img loading="lazy" src="' + escapeHtml(item.url) + '" alt="' + escapeHtml(item.name) + '"></div>' +
      '<div class="preview-meta">' +
      '<div class="preview-step">' + escapeHtml(progress.step) + '</div>' +
      '<div class="preview-epoch">' + escapeHtml(progress.epoch) + '</div>' +
      '<div class="preview-file" title="' + escapeHtml(item.name) + '">' + escapeHtml(item.name) + '</div></div>' +
      '</div>';
  }).join("") + '</div>';
}

function renderStatus(status) {
  document.getElementById("updatedAt").textContent = status.time || "";
  const metrics = status.metrics || {};
  const error = status.error || status.log_error || "";
  const guiWarning = status.gui_warning || "";
  const errorBox = document.getElementById("errorBox");
  errorBox.textContent = error || guiWarning;
  errorBox.classList.toggle("alert--error", Boolean(error));
  errorBox.classList.toggle("alert--warn", Boolean(!error && guiWarning));
  errorBox.style.display = (error || guiWarning) ? "block" : "none";
  renderHero(status);
  renderCards(status);
  renderTrainParams(status);
  renderLossChart(metrics, status);
  renderPreviews(status.previews, metrics);
  const resultFilesEl = document.getElementById("resultFiles");
  const resultKey = JSON.stringify({
    state: status.state,
    scope: status.output_scope,
    primary: status.outputs_primary,
    other: status.outputs_other,
    outputs: status.outputs
  });
  if (resultKey !== lastResultKey) {
    resultFilesEl.innerHTML = renderResult(status);
    bindResultActions(resultFilesEl);
    lastResultKey = resultKey;
  }
  renderResultDuration(status, metrics);

  const logLines = status.log_lines || [];
  const hasLogError = Boolean(error || metrics.has_error);
  const hasLogWarning = Boolean(metrics.needs_attention || metrics.progress_stalled || metrics.has_warning);
  logSummary.textContent = hasLogError
    ? "训练日志（检测到错误，已自动展开）"
    : (hasLogWarning ? "训练日志（有警告，未自动展开）" : "训练日志（正常，最近 " + logLines.length + " 行）");
  if (hasLogError) logDetails.open = true;

  const wasNearBottom = autoFollow || isNearBottom(logBox);
  const logText = logLines.slice(-180).join("\n") || "暂无训练日志。";
  if (logText !== lastLogText) {
    logBox.textContent = logText;
    lastLogText = logText;
    if (wasNearBottom) scrollToLatest();
  }
}

async function pollStatus() {
  try {
    const resp = await fetch("/api/status?ts=" + Date.now(), { cache: "no-store" });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    renderStatus(await resp.json());
  } catch (err) {
    const errorBox = document.getElementById("errorBox");
    errorBox.textContent = "刷新监控状态失败: " + err;
    errorBox.style.display = "block";
  }
}

renderPreviewToggle();
bindLightboxEvents();
pollStatus();
setInterval(pollStatus, 2000);
