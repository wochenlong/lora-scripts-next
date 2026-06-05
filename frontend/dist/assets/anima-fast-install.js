/**
 * Anima Fast plugin install panel: status polling, install trigger, guide toggle.
 * Loaded globally so SPA navigation to /lora/anima-fast works (not only full page load).
 */
(function () {
  if (window.__ANIMA_FAST_INSTALL_GUARD__) return;
  window.__ANIMA_FAST_INSTALL_GUARD__ = true;

  const CONFIRM =
    "Anima Fast 为进阶实验插件，需 NVIDIA GPU、约 16GB+ 显存，并会下载独立 Python 环境（数 GB）。\n\n确认已了解并继续安装？";

  let last = { feature_enabled: true, state: "unknown" };
  let es = null;
  let tmr = null;
  let scheduled = false;
  let observedPath = location.pathname;

  function q(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  function isFastPage() {
    return /^\/lora\/anima-fast(\.html|\.md)?$/.test(location.pathname);
  }

  function isStandardAnimaPage() {
    return /^\/lora\/sd3(\.html|\.md)?$/.test(location.pathname);
  }

  function isAnimaDiagnosticsPage() {
    return isFastPage() || isStandardAnimaPage();
  }

  function markPage() {
    document.body.classList.toggle("anima-fast-page", isFastPage());
    document.body.classList.toggle("anima-standard-page", isStandardAnimaPage());
    document.body.classList.toggle("anima-diagnostics-page", isAnimaDiagnosticsPage());
  }

  function setControls(d) {
    if (!isFastPage()) return;
    const kill = !d.feature_enabled;
    const working = d.state === "installing" || d.state === "auditing";
    const ready = d.state === "ready";
    q("[data-anima-fast-install]").forEach(function (b) {
      b.disabled = kill || working;
      b.setAttribute("aria-disabled", b.disabled ? "true" : "false");
    });
    q(".right-container button").forEach(function (b) {
      const t = (b.textContent || "").trim();
      if (
        t === "开始训练" ||
        t === "✨加载训练预设✨" ||
        t === "导入配置文件" ||
        t === "保存参数" ||
        t === "Start training" ||
        t === "Load training preset" ||
        t === "Import config" ||
        t === "Save parameters"
      ) {
        b.disabled = kill || !ready;
        b.setAttribute("aria-disabled", b.disabled ? "true" : "false");
      }
    });
    document.body.classList.toggle("anima-fast-disabled", kill || !ready);
  }

  function label(d) {
    if (!d.feature_enabled) return "功能已关闭";
    if (d.state === "ready") return "插件已就绪";
    if (d.state === "installing") return "安装中";
    if (d.state === "auditing") return "审计中";
    if (d.state === "broken") return "需修复";
    if (d.state === "installed_unverified") return "待审计";
    return "进阶插件 · 待开启";
  }

  function appendLog(x) {
    const p = document.querySelector("[data-anima-fast-log]");
    if (!p) return;
    p.hidden = false;
    p.textContent += (p.textContent ? "\n" : "") + x;
    p.scrollTop = p.scrollHeight;
  }

  function formatFastRunFail(json) {
    if (!json || json.status === "success") return "";
    const parts = [];
    if (json.message) parts.push(String(json.message));
    const errs = json.data && json.data.errors;
    if (Array.isArray(errs)) {
      errs.slice(0, 6).forEach(function (e) {
        const line = String(e || "").trim();
        if (line && parts.indexOf(line) === -1) parts.push(line);
      });
    }
    return parts.join(" | ");
  }

  function ensureDiagnosticsPanel() {
    if (!isAnimaDiagnosticsPage()) return null;
    let panel = document.querySelector("[data-anima-diagnostics]");
    if (panel) return panel;
    panel = document.createElement("div");
    panel.className = "anima-diagnostics";
    panel.setAttribute("data-anima-diagnostics", "");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.hidden = true;
    panel.innerHTML =
      '<div class="anima-diagnostics__backdrop" data-anima-diagnostics-close></div>' +
      '<div class="anima-diagnostics__card">' +
      '<div class="anima-diagnostics__head">' +
      '<div class="anima-diagnostics__icon" aria-hidden="true">!</div>' +
      '<div class="anima-diagnostics__title-wrap">' +
      '<strong data-anima-diagnostics-title>训练诊断</strong>' +
      '<p>预检查发现以下问题，请修复后重试</p>' +
      "</div>" +
      '<button type="button" class="el-button el-button--primary is-plain anima-diagnostics__copy" data-anima-diagnostics-copy>复制全部</button>' +
      '<button type="button" class="anima-diagnostics__close" data-anima-diagnostics-close aria-label="关闭">×</button>' +
      "</div>" +
      '<div class="anima-diagnostics__summary" data-anima-diagnostics-message></div>' +
      '<div class="anima-diagnostics__section" data-anima-diagnostics-errors-section>' +
      '<div class="anima-diagnostics__section-title"><span>错误</span><span data-anima-diagnostics-errors-count>0</span></div>' +
      '<div class="anima-diagnostics__items" data-anima-diagnostics-errors></div>' +
      "</div>" +
      '<div class="anima-diagnostics__section anima-diagnostics__section--warning" data-anima-diagnostics-warnings-section>' +
      '<div class="anima-diagnostics__section-title"><span>警告</span><span data-anima-diagnostics-warnings-count>0</span></div>' +
      '<div class="anima-diagnostics__items" data-anima-diagnostics-warnings></div>' +
      "</div>" +
      '<div class="anima-diagnostics__section anima-diagnostics__section--json">' +
      '<div class="anima-diagnostics__section-title"><span>详细诊断 / JSON</span>' +
      '<button type="button" class="el-button el-button--small is-plain anima-diagnostics__json-copy" data-anima-diagnostics-copy-json>复制 JSON</button>' +
      "</div>" +
      '<div class="anima-diagnostics__json-wrap">' +
      '<div class="anima-diagnostics__gutter" data-anima-diagnostics-lines></div>' +
      '<pre class="anima-diagnostics__json" data-anima-diagnostics-json></pre>' +
      "</div>" +
      '<div class="anima-diagnostics__foot"><button type="button" class="el-button el-button--primary" data-anima-diagnostics-close>关闭</button></div>' +
      "</div>";
    document.body.appendChild(panel);
    return panel;
  }

  function extractDiagnosticPayload(json, cfg, url) {
    if (!json || json.status === "success") return null;
    const errors = json.data ? json.data.errors : null;
    const warnings = json.data ? json.data.warnings : null;
    const facts = json.data ? json.data.facts : null;
    return {
      page: isFastPage() ? "anima-fast" : "anima-standard",
      request: url || "",
      train_type: cfg && cfg.model_train_type,
      message: json.message || "未知错误",
      errors: Array.isArray(errors) ? errors : [],
      warnings: Array.isArray(warnings) ? warnings : [],
      facts: facts || null,
      response: json,
    };
  }

  function isAnimaTrainConfig(cfg) {
    return cfg && (cfg.model_train_type === "anima-lora" || cfg.model_train_type === "anima-lora-fast");
  }

  function showRunDiagnostics(payload) {
    if (!payload) return;
    const panel = ensureDiagnosticsPanel();
    if (!panel) return;
    const title = panel.querySelector("[data-anima-diagnostics-title]");
    const message = panel.querySelector("[data-anima-diagnostics-message]");
    const errors = panel.querySelector("[data-anima-diagnostics-errors]");
    const warnings = panel.querySelector("[data-anima-diagnostics-warnings]");
    const errorsSection = panel.querySelector("[data-anima-diagnostics-errors-section]");
    const warningsSection = panel.querySelector("[data-anima-diagnostics-warnings-section]");
    const errorsCount = panel.querySelector("[data-anima-diagnostics-errors-count]");
    const warningsCount = panel.querySelector("[data-anima-diagnostics-warnings-count]");
    const pre = panel.querySelector("[data-anima-diagnostics-json]");
    const lines = panel.querySelector("[data-anima-diagnostics-lines]");
    const text = JSON.stringify(payload, null, 2);
    const titleText = payload.page === "anima-fast" ? "Anima Fast 训练诊断" : "Anima 标准模式训练诊断";
    const fullText = [
      titleText,
      payload.message || "未知错误",
      payload.errors.length ? "\n错误:\n" + payload.errors.map(function (x) { return "- " + x; }).join("\n") : "",
      payload.warnings.length ? "\n警告:\n" + payload.warnings.map(function (x) { return "- " + x; }).join("\n") : "",
      "\nJSON:\n" + text,
    ].filter(Boolean).join("\n");
    panel.hidden = false;
    panel.dataset.diagnosticJson = text;
    panel.dataset.diagnosticFullText = fullText;
    if (title) title.textContent = titleText;
    if (message) message.textContent = payload.message || "未知错误";
    if (errors) {
      errors.innerHTML = "";
      payload.errors.slice(0, 8).forEach(function (item) {
        const row = document.createElement("div");
        row.className = "anima-diagnostics__item";
        row.innerHTML = '<span class="anima-diagnostics__item-icon">×</span><code></code>';
        row.querySelector("code").textContent = String(item);
        errors.appendChild(row);
      });
      if (errorsSection) errorsSection.hidden = !payload.errors.length;
      if (errorsCount) errorsCount.textContent = String(payload.errors.length);
    }
    if (warnings) {
      warnings.innerHTML = "";
      payload.warnings.slice(0, 8).forEach(function (item) {
        const row = document.createElement("div");
        row.className = "anima-diagnostics__item anima-diagnostics__item--warning";
        row.innerHTML = '<span class="anima-diagnostics__item-icon">!</span><code></code>';
        row.querySelector("code").textContent = String(item);
        warnings.appendChild(row);
      });
      if (warningsSection) warningsSection.hidden = !payload.warnings.length;
      if (warningsCount) warningsCount.textContent = String(payload.warnings.length);
    }
    if (pre) pre.textContent = text;
    if (lines) {
      lines.innerHTML = "";
      text.split("\n").forEach(function (_, index) {
        const line = document.createElement("span");
        line.textContent = String(index + 1);
        lines.appendChild(line);
      });
    }
    if (payload.page === "anima-fast") {
      appendLog("[训练] " + (payload.errors[0] || payload.message || "未知错误"));
    }
  }

  async function copyDiagnosticText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return "copied";
      } catch (_) {}
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_) {
      ok = false;
    } finally {
      ta.remove();
    }
    return ok ? "copied" : "failed";
  }

  function selectDiagnosticsJson(panel) {
    const pre = panel && panel.querySelector("[data-anima-diagnostics-json]");
    if (!pre || !window.getSelection || !document.createRange) return false;
    const range = document.createRange();
    range.selectNodeContents(pre);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  }

  const COMPILE_WARN_TEXT =
    "compile_mode=full 与「梯度检查点」不能同时开启。已自动调整：请保持 compile 模式为 blocks，或关闭梯度检查点后再选 full。";
  let compileGuardBusy = false;
  let lastCompileWarnShown = false;

  function findFormItem(labelNeedle) {
    return Array.from(document.querySelectorAll(".example-container .el-form-item, .example-container .k-schema-item")).find(function (row) {
      const lab = row.querySelector(".el-form-item__label, .k-schema-main");
      const text = ((lab && lab.textContent) || row.textContent || "").trim();
      return text.indexOf(labelNeedle) !== -1;
    });
  }

  function readSelectText(row) {
    if (!row) return "";
    const item = row.querySelector(".el-select .el-select__selected-item span");
    if (item) return (item.textContent || "").trim();
    const wrap = row.querySelector(".el-select__wrapper, .el-select");
    return wrap ? (wrap.textContent || "").trim() : "";
  }

  function readSwitchOn(row) {
    if (!row) return false;
    const input = row.querySelector('input[type="checkbox"]');
    if (input) return !!input.checked;
    const sw = row.querySelector(".el-switch");
    return sw ? sw.classList.contains("is-checked") : false;
  }

  function auditImports() {
    const audit = last && last.facts && last.facts.audit;
    const facts = audit && audit.facts;
    const anima = facts && facts.anima;
    return (anima && anima.imports) || {};
  }

  function importAvailability(name) {
    const imports = auditImports();
    if (!Object.prototype.hasOwnProperty.call(imports, name)) return null;
    return imports[name] === true;
  }

  function flashUnavailable() {
    return importAvailability("flash_attn") === false;
  }

  function quantoUnavailable() {
    return importAvailability("optimum.quanto") === false;
  }

  function setSwitchOn(row, on) {
    if (!row || readSwitchOn(row) === on) return;
    const sw = row.querySelector(".el-switch");
    if (sw) sw.click();
  }

  function pickSelectOption(row, want) {
    if (!row) return;
    const select = row.querySelector(".el-select");
    if (!select) return;
    if (readSelectText(row) === want) return;
    select.click();
    window.setTimeout(function () {
      const items = Array.from(document.querySelectorAll(".el-select-dropdown__item"));
      const hit = items.find(function (el) {
        return (el.textContent || "").trim() === want;
      });
      if (hit) hit.click();
    }, 60);
  }

  function markUnavailableDropdownOptions() {
    if (!isFastPage()) return;
    const disabled = [];
    if (flashUnavailable()) disabled.push({ text: "flash", reason: "flash-attn 不可用，请先修复插件环境或使用 torch/xformers" });
    if (quantoUnavailable()) disabled.push({ text: "Automagic", reason: "Automagic 需要 optimum-quanto，请先修复插件环境或使用 AdamW8bit" });
    if (!disabled.length) return;
    window.setTimeout(function () {
      q(".el-select-dropdown__item").forEach(function (item) {
        const text = (item.textContent || "").trim();
        const hit = disabled.find(function (entry) {
          return entry.text === text;
        });
        if (!hit) return;
        item.classList.add("anima-fast-option-disabled");
        item.setAttribute("aria-disabled", "true");
        item.setAttribute("title", hit.reason);
        item.setAttribute("data-anima-fast-disabled-reason", hit.reason);
      });
    }, 80);
  }

  function syncAuditOptionGuards() {
    if (!isFastPage()) return;
    const attnRow = findFormItem("Attention 加速实现");
    const optimizerRow = findFormItem("优化器");
    if (flashUnavailable() && readSelectText(attnRow) === "flash") {
      pickSelectOption(attnRow, "torch");
      appendLog("[warning] flash-attn 不可用，已将 Attention 从 flash 改为 torch");
    }
    if (quantoUnavailable() && readSelectText(optimizerRow) === "Automagic") {
      pickSelectOption(optimizerRow, "AdamW8bit");
      appendLog("[warning] optimum-quanto 不可用，已将优化器从 Automagic 改为 AdamW8bit");
    }
    attnRow && attnRow.classList.toggle("anima-fast-audit-limited", flashUnavailable());
    optimizerRow && optimizerRow.classList.toggle("anima-fast-audit-limited", quantoUnavailable());
  }

  function ensureCompileWarnBanner() {
    const form = document.querySelector(".example-container .schema-container .el-form, .example-container .schema-container form");
    if (!form || form.querySelector("[data-anima-fast-compile-warn]")) return;
    const banner = document.createElement("div");
    banner.className = "anima-fast-compile-warn";
    banner.setAttribute("data-anima-fast-compile-warn", "");
    banner.hidden = true;
    banner.textContent = COMPILE_WARN_TEXT;
    form.insertBefore(banner, form.firstChild);
  }

  function showCompileWarn(show) {
    ensureCompileWarnBanner();
    const banner = document.querySelector("[data-anima-fast-compile-warn]");
    if (!banner) return;
    banner.hidden = !show;
    if (show && !lastCompileWarnShown) {
      appendLog("[warning] " + COMPILE_WARN_TEXT);
      lastCompileWarnShown = true;
    }
    if (!show) lastCompileWarnShown = false;
  }

  function syncCompileGuard() {
    if (!isFastPage() || compileGuardBusy) return;
    const compileRow = findFormItem("compile 模式");
    const gcRow = findFormItem("梯度检查点");
    if (!compileRow && !gcRow) return;

    const compileMode = readSelectText(compileRow);
    const gcOn = readSwitchOn(gcRow);
    const conflict = compileMode === "full" && gcOn;

    compileRow && compileRow.classList.toggle("anima-fast-compile-locked", gcOn);
    gcRow && gcRow.classList.toggle("anima-fast-compile-locked", compileMode === "full");

    if (!conflict) {
      showCompileWarn(false);
      return;
    }

    compileGuardBusy = true;
    try {
      if (gcOn && compileMode === "full") {
        pickSelectOption(compileRow, "blocks");
      } else if (compileMode === "full") {
        setSwitchOn(gcRow, false);
      }
      showCompileWarn(true);
    } finally {
      window.setTimeout(function () {
        compileGuardBusy = false;
      }, 120);
    }
  }

  function initCompileModeGuard() {
    if (!isFastPage()) return;
    ensureCompileWarnBanner();
    syncCompileGuard();
  }

  function patchRunRequestBody(init) {
    if (!init || !init.body || typeof init.body !== "string") return init;
    try {
      const cfg = JSON.parse(init.body);
      if (cfg.model_train_type !== "anima-lora-fast") return init;
      if (cfg.attn_mode === "flash" && flashUnavailable()) {
        cfg.attn_mode = "torch";
        appendLog("[warning] 已阻止 flash-attn 不可用组合，Attention 自动改为 torch");
      }
      if (cfg.optimizer_type === "Automagic" && quantoUnavailable()) {
        cfg.optimizer_type = "AdamW8bit";
        appendLog("[warning] 已阻止 Automagic 缺少 optimum-quanto 组合，优化器自动改为 AdamW8bit");
      }
      if (cfg.skip_cache_check && (cfg.cache_latents || cfg.cache_text_encoder_outputs)) {
        cfg.cache_latents = false;
        cfg.cache_text_encoder_outputs = false;
        cfg.skip_cache_check = false;
        appendLog("[warning] 已阻止 cache 与 skip_cache_check 同时开启，相关开关已自动关闭");
      }
      if (cfg.compile_mode === "full" && cfg.gradient_checkpointing) {
        cfg.compile_mode = "blocks";
        const next = Object.assign({}, init, { body: JSON.stringify(cfg) });
        appendLog("[warning] 已阻止 full + 梯度检查点 组合，compile_mode 自动改为 blocks");
        return next;
      }
      return Object.assign({}, init, { body: JSON.stringify(cfg) });
    } catch (_) {}
    return init;
  }

  if (!window.__ANIMA_FAST_RUN_FETCH_PATCH__) {
    window.__ANIMA_FAST_RUN_FETCH_PATCH__ = true;
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : input && input.url ? input.url : "";
      const isRun =
        url.indexOf("/api/run") !== -1 && init && String(init.method || "GET").toUpperCase() === "POST";
      const isPreflight =
        url.indexOf("/api/plugins/anima-lora/preflight") !== -1 &&
        init &&
        String(init.method || "GET").toUpperCase() === "POST";
      let requestConfig = null;
      if ((isRun || isPreflight) && init && typeof init.body === "string") {
        try {
          requestConfig = JSON.parse(init.body);
        } catch (_) {}
      }
      if (isRun && isFastPage() && init) {
        init = patchRunRequestBody(init);
        if (typeof init.body === "string") {
          try {
            requestConfig = JSON.parse(init.body);
          } catch (_) {}
        }
      }
      return nativeFetch(input, init).then(function (res) {
        const isAnimaRun =
          isRun &&
          isAnimaDiagnosticsPage() &&
          isAnimaTrainConfig(requestConfig);
        const isAnimaFastPreflight = isPreflight && isFastPage();
        if (!isAnimaRun && !isAnimaFastPreflight) return res;
        return res
          .clone()
          .json()
          .then(function (json) {
            if (json && json.status === "fail") {
              const payload = extractDiagnosticPayload(json, requestConfig, url);
              showRunDiagnostics(payload);
              if (isFastPage()) {
                const msg = formatFastRunFail(json);
                if (msg) appendLog("[训练] " + msg);
              }
            }
            return res;
          })
          .catch(function () {
            return res;
          });
      });
    };
  }

  function apply(d) {
    last = d || last;
    setControls(last);
    const n = document.querySelector("[data-anima-fast-status]");
    if (n) n.textContent = label(last);
    const a = last.facts && last.facts.audit;
    if (a && !a.ok && a.errors) appendLog("[audit] " + a.errors.join("; "));
    syncAuditOptionGuards();
  }

  async function status() {
    if (!isFastPage()) return;
    try {
      const r = await fetch("/api/plugins/anima-lora/status");
      const j = await r.json();
      apply(Object.assign({ feature_enabled: true }, j.data || { state: "unknown" }));
    } catch (e) {
      const n = document.querySelector("[data-anima-fast-status]");
      if (n) n.textContent = "状态检查失败";
    }
  }

  function scheduleStatus() {
    if (!isFastPage()) return;
    if (scheduled) return;
    scheduled = true;
    setTimeout(function () {
      scheduled = false;
      const pathChanged = observedPath !== location.pathname;
      observedPath = location.pathname;
      markPage();
      initGuideToggle();
      ensureSidebarFastLink();
      initCompileModeGuard();
      syncAuditOptionGuards();
      if (pathChanged) status();
    }, 120);
  }

  function openLog(url) {
    if (!url || !window.EventSource) return;
    if (es) es.close();
    appendLog("[log] streaming " + url);
    es = new EventSource(url);
    es.onmessage = function (e) {
      try {
        const d = JSON.parse(e.data);
        if (d.text) appendLog(d.text);
        if (d.done) {
          appendLog("[log] done");
          es.close();
          es = null;
          if (tmr) {
            clearInterval(tmr);
            tmr = null;
          }
          status();
        }
      } catch (_) {
        appendLog(e.data);
      }
    };
    es.onerror = function () {
      appendLog("[log] stream disconnected");
      if (es) {
        es.close();
        es = null;
      }
      status();
    };
  }

  function initGuideToggle() {
    if (!isFastPage()) return;
    q("[data-anima-fast-guide-toggle]").forEach(function (t) {
      const p = t.closest(".anima-fast-guide-collapsible");
      const b = p && p.querySelector(".anima-fast-dataset-guide__body");
      if (!b) return;
      let o = false;
      try {
        o = localStorage.getItem("anima-fast-guide-open") === "1";
      } catch (_) {}
      b.hidden = !o;
      t.setAttribute("aria-expanded", o ? "true" : "false");
      p.classList.toggle("is-open", o);
    });
  }

  function ensureSidebarFastLink() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return;
    if (
      sidebar.querySelector('a[href="/lora/anima-fast.html"]') ||
      sidebar.querySelector('a[href="/lora/anima-fast.md"]')
    ) {
      return;
    }
    const finetune = sidebar.querySelector('a[href="/lora/anima-finetune.md"]');
    const anchorLi = finetune && finetune.closest("li");
    const group = anchorLi && anchorLi.parentElement;
    if (!anchorLi || !group) return;

    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = "/lora/anima-fast.html";
    a.className = "sidebar-item sidebar-heading";
    a.setAttribute("aria-label", "Anima LoRA Fast");
    a.appendChild(document.createTextNode(" Anima Fast "));
    li.appendChild(a);
    anchorLi.insertAdjacentElement("afterend", li);
  }

  document.addEventListener("click", async function (e) {
    const guideBtn = e.target && e.target.closest && e.target.closest("[data-anima-fast-guide-toggle]");
    if (guideBtn && isFastPage()) {
      const p = guideBtn.closest(".anima-fast-guide-collapsible");
      const b = p && p.querySelector(".anima-fast-dataset-guide__body");
      if (b) {
        const o = b.hidden;
        b.hidden = !o;
        guideBtn.setAttribute("aria-expanded", o ? "true" : "false");
        p.classList.toggle("is-open", o);
        try {
          localStorage.setItem("anima-fast-guide-open", o ? "1" : "0");
        } catch (_) {}
      }
      return;
    }

    const closeBtn = e.target && e.target.closest && e.target.closest("[data-anima-diagnostics-close]");
    if (closeBtn && isAnimaDiagnosticsPage()) {
      const panel = closeBtn.closest("[data-anima-diagnostics]") || document.querySelector("[data-anima-diagnostics]");
      if (panel) panel.hidden = true;
      return;
    }

    const copyJsonBtn = e.target && e.target.closest && e.target.closest("[data-anima-diagnostics-copy-json]");
    if (copyJsonBtn && isAnimaDiagnosticsPage()) {
      const panel = copyJsonBtn.closest("[data-anima-diagnostics]");
      const text = (panel && panel.dataset.diagnosticJson) || "";
      if (!text) return;
      const copyResult = await copyDiagnosticText(text);
      if (copyResult === "copied") {
        copyJsonBtn.textContent = "已复制";
        setTimeout(function () {
          copyJsonBtn.textContent = "复制 JSON";
        }, 1600);
      } else if (selectDiagnosticsJson(panel)) {
        copyJsonBtn.textContent = "已选中，可 Ctrl+C";
        setTimeout(function () {
          copyJsonBtn.textContent = "复制 JSON";
        }, 2200);
      } else {
        copyJsonBtn.textContent = "复制失败";
        setTimeout(function () {
          copyJsonBtn.textContent = "复制 JSON";
        }, 1600);
      }
      return;
    }

    const copyBtn = e.target && e.target.closest && e.target.closest("[data-anima-diagnostics-copy]");
    if (copyBtn && isAnimaDiagnosticsPage()) {
      const panel = copyBtn.closest("[data-anima-diagnostics]");
      const text = (panel && (panel.dataset.diagnosticFullText || panel.dataset.diagnosticJson)) || "";
      if (!text) return;
      const copyResult = await copyDiagnosticText(text);
      if (copyResult === "copied") {
        copyBtn.textContent = "已复制";
        setTimeout(function () {
          copyBtn.textContent = "复制全部";
        }, 1600);
      } else if (selectDiagnosticsJson(panel)) {
        copyBtn.textContent = "已选中，可 Ctrl+C";
        setTimeout(function () {
          copyBtn.textContent = "复制全部";
        }, 2200);
      } else {
        copyBtn.textContent = "复制失败";
        setTimeout(function () {
          copyBtn.textContent = "复制全部";
        }, 1600);
      }
      return;
    }

    const installBtn = e.target && e.target.closest && e.target.closest("[data-anima-fast-install]");
    if (!installBtn || !isFastPage()) return;
    if (!last.feature_enabled) return;
    if (!window.confirm(CONFIRM)) return;

    installBtn.disabled = true;
    const statusEl = document.querySelector("[data-anima-fast-status]");
    const logEl = document.querySelector("[data-anima-fast-log]");
    if (logEl) {
      logEl.hidden = false;
      logEl.textContent = "";
    }
    if (statusEl) statusEl.textContent = "安装任务启动中";

    try {
      const r = await fetch("/api/plugins/anima-lora/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: false }),
      });
      const j = await r.json();
      if (j.status !== "success") {
        if (statusEl) statusEl.textContent = j.message || "安装失败";
        appendLog("[error] " + (j.message || "install failed"));
        return;
      }
      const d = j.data || {};
      if (statusEl) statusEl.textContent = "安装中";
      appendLog("[task] " + (d.task_id || "unknown"));
      openLog(
        d.log_stream ||
          d.log_stream_url ||
          (d.task_id ? "/api/plugins/anima-lora/install/log/stream/" + d.task_id : "")
      );
      if (tmr) clearInterval(tmr);
      tmr = setInterval(status, 2000);
      status();
    } catch (err) {
      if (statusEl) statusEl.textContent = "安装失败";
      appendLog("[error] " + err);
    } finally {
      setTimeout(function () {
        setControls(last);
      }, 250);
    }
  });

  document.addEventListener(
    "change",
    function () {
      if (isFastPage()) syncCompileGuard();
    },
    true
  );
  document.addEventListener(
    "click",
    function (e) {
      if (!isFastPage()) return;
      const disabledItem = e.target && e.target.closest && e.target.closest(".el-select-dropdown__item.anima-fast-option-disabled");
      if (disabledItem) {
        e.preventDefault();
        e.stopPropagation();
        appendLog("[warning] " + (disabledItem.getAttribute("data-anima-fast-disabled-reason") || "该选项当前不可用"));
        return;
      }
      markUnavailableDropdownOptions();
      window.setTimeout(function () {
        syncCompileGuard();
        syncAuditOptionGuards();
        markUnavailableDropdownOptions();
      }, 80);
    },
    true
  );

  new MutationObserver(scheduleStatus).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  window.addEventListener("popstate", scheduleStatus);
  window.addEventListener("hashchange", scheduleStatus);

  function recoverEmptySchemaForm() {
    if (!isFastPage()) return;
    const form = document.querySelector(".example-container .schema-container form");
    if (!form || form.querySelector(".k-schema-item,.el-form-item")) return;
    const schemas = localStorage.getItem("schemas") || "";
    if (!schemas.includes("anima-lora-fast")) return;
    if (sessionStorage.getItem("anima-fast-schema-reload") === "1") return;
    sessionStorage.setItem("anima-fast-schema-reload", "1");
    location.reload();
  }

  function boot() {
    markPage();
    initGuideToggle();
    ensureSidebarFastLink();
    syncAuditOptionGuards();
    status();
    setTimeout(recoverEmptySchemaForm, 2500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  setTimeout(boot, 0);
})();
