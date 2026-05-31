/**
 * Sidebar / home hub locale labels when UI is English (en-US).
 * Schema forms use vue-i18n; VuePress sidebar SSR text stays Chinese without this patch.
 */
(function () {
  const STORAGE_KEY = "sd-trainer-ui-locale";

  const ZH_TO_EN = {
    训练: "Training",
    "LoRA训练": "LoRA Training",
    "LoRA 训练": "LoRA Training",
    全量微调: "Full Finetune",
    工具与调试: "Tools",
    数据集打标: "Dataset Tagging",
    标签编辑: "Tag Editor",
    "LoRA 脚本工具": "LoRA Scripts",
    帮助: "Help",
    新手上路: "Getting Started",
    训练参数说明: "Training Parameters",
    其他: "More",
    "UI 设置": "UI Settings",
    关于: "About",
    更新日志: "Changelog",
    训练监控: "Train Monitor",
    "自动端口 · 实时日志": "Auto port · Live logs",
    "DiT · 主推": "DiT · Recommended",
    "DiT full finetune · 高显存": "DiT full finetune · High VRAM",
    "SDXL Finetune · Dreambooth": "SDXL finetune · Dreambooth",
    "SD1.5 / SDXL LoRA": "SD1.5 / SDXL LoRA",
    "Flux LoRA": "Flux LoRA",
    "下一代训练 WebUI": "Next-gen training WebUI",
    "Anima DiT 全量微调（full finetune）": "Anima DiT full finetune",
    "更新完整 DiT 权重，适合进阶玩家训练，需充足样本与高显存":
      "Updates full DiT weights; for advanced users with enough data and VRAM (~24 GB)",
    "Anima Finetune 专家模式": "Anima Finetune · Expert mode",
    "Anima LoRA 训练 专家模式": "Anima LoRA · Expert mode",
    "Anima DiT 模型 LoRA 训练 专家模式": "Anima LoRA training · Expert mode",
    "Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数":
      "Anima DiT LoRA entry (Qwen3 + T5 + Anima-specific options)",
    "参数预览": "Parameter preview",
    全部重置: "Reset all",
    保存参数: "Save parameters",
    读取参数: "Load parameters",
    下载配置文件: "Download config",
    导入配置文件: "Import config",
    "✨加载训练预设✨": "Load training preset",
    开始训练: "Start training",
    终止训练: "Stop training",
    "帮助 → 新手上路": "Help → Getting started",
    "秋叶用户迁移说明": "Migration from Akiba lora-scripts",
    参数释义: "Parameter glossary",
    "Fast 模式": "Fast mode",
    传统模式: "Standard mode",
    标准模式: "Standard mode",
    "Anima LoRA · Fast 模式": "Anima LoRA · Fast mode",
    "插件加速 · 进阶": "Plugin · Advanced",
    开启插件: "Enable plugin",
    检查中: "Checking…",
    "Anima 高速 LoRA 训练（进阶插件）。需单独安装 runtime，仅支持标准 LoRA。显存建议 16GB+，首次安装需下载数 GB 依赖。":
      "Anima fast LoRA training (advanced plugin). Requires a separate runtime install; standard LoRA only. 16 GB+ VRAM recommended; first install downloads several GB of dependencies.",
    "Fast 模式训练教程": "Fast mode training guide",
    "（安装、数据路径、故障排除）": " (install, data paths, troubleshooting)",
    标准 Kohya 模式: "Standard Kohya mode",
    "数据集路径说明（与 Kohya 不同）": "Dataset paths (differs from Kohya)",
    "Fast 训练实际读取 resized 目录": "Fast training reads the resized directory",
    "里的 bucket 预处理图，不是直接读原图。": " for bucket-preprocessed images, not the original files directly.",
    训练图片目录: "Training image folder",
    "：原图 + caption（如 ": ": originals + captions (e.g. ",
    "resized 目录": "Resized folder",
    "：训练真正用到的 bucket PNG；": ": bucket PNGs used for training; ",
    留空: "leave empty",
    "时自动写入 ": " writes to ",
    "（同一数据集可复用）": " (reusable for the same dataset)",
    "可以填同一路径吗？": "Can both fields use the same path?",
    "可以。若该目录已是 bucket 预处理后的 PNG + caption，两处可填": "Yes. If the folder already has bucket-preprocessed PNGs + captions, both fields can use ",
    相同路径: "the same path",
    "输出 / cache 目录不存在时会自动创建。左侧「cache_latents」等保持关闭，除非已完成完整 preprocess。":
      "Output / cache folders are created if missing. Keep cache_latents off on the left unless full preprocess is done.",
    "Fast 训练引擎来自开源项目 ": "The Fast training engine comes from the open-source project ",
    "。感谢原作者与社区的开发与分享；本页以可选插件形式集成，遵循各自开源许可。":
      ". Thanks to the original author and community for developing and sharing it; integrated here as an optional plugin under their respective open-source licenses.",
  };

  const FAST_DOC_URL =
    "https://github.com/wochenlong/lora-scripts-next/blob/main/docs/anima-fast.md";

  const ANIMA_FAST = {
    zh: {
      title: "Anima LoRA · Fast 模式",
      intro:
        "Anima 高速 LoRA 训练（进阶插件）。需单独安装 runtime，仅支持标准 LoRA。显存建议 16GB+，首次安装需下载数 GB 依赖。",
      kohyaNote: "标准模式（Kohya）见 /lora/sd3.html",
      credit:
        '<p class="anima-fast-credit">Fast 训练引擎来自开源项目 <a href="https://github.com/sorryhyun/anima_lora" target="_blank" rel="noopener noreferrer">sorryhyun/anima_lora</a>。感谢原作者与社区的开发与分享；本页以可选插件形式集成，遵循各自开源许可。</p>',
      docLinks:
        '<p class="anima-fast-doc-links"><a href="' +
        FAST_DOC_URL +
        '" target="_blank" rel="noopener noreferrer">Fast 模式训练教程</a>（安装、数据路径、故障排除） · <a href="/lora/sd3.html">标准 Kohya 模式</a></p>',
      guide:
        '<div class="anima-fast-guide-collapsible"><button type="button" class="anima-fast-guide-toggle" data-anima-fast-guide-toggle aria-expanded="false"><span class="anima-fast-guide-toggle__icon" aria-hidden="true">▸</span><span class="anima-fast-guide-toggle__label">数据集路径说明（与 Kohya 不同）</span></button><div class="anima-fast-dataset-guide anima-fast-dataset-guide__body" hidden><p>Fast 训练<strong>实际读取 resized 目录</strong>里的 bucket 预处理图，不是直接读原图。</p><ul><li><strong>训练图片目录</strong>：原图 + caption（如 <code>data/xxx/子文件夹/</code>）</li><li><strong>resized 目录</strong>：训练真正用到的 bucket PNG；<strong>留空</strong>时自动写入 <code>.cache/anima_fast/&lt;数据集路径&gt;/resized</code>（同一数据集可复用）</li></ul><p class="anima-fast-dataset-guide__highlight"><strong>可以填同一路径吗？</strong>可以。若该目录已是 bucket 预处理后的 PNG + caption，两处可填<strong>相同路径</strong>。</p><p class="anima-fast-dataset-guide__note">输出 / cache 目录不存在时会自动创建。左侧「cache_latents」等保持关闭，除非已完成完整 preprocess。</p></div></div>',
    },
    en: {
      title: "Anima LoRA · Fast mode",
      intro:
        "Anima fast LoRA training (advanced plugin). Requires a separate runtime install; standard LoRA only. 16 GB+ VRAM recommended; first install downloads several GB of dependencies.",
      kohyaNote: "Standard Kohya mode: /lora/sd3.html",
      credit:
        '<p class="anima-fast-credit">The Fast training engine comes from the open-source project <a href="https://github.com/sorryhyun/anima_lora" target="_blank" rel="noopener noreferrer">sorryhyun/anima_lora</a>. Thanks to the original author and community for developing and sharing it; integrated here as an optional plugin under their respective open-source licenses.</p>',
      docLinks:
        '<p class="anima-fast-doc-links"><a href="' +
        FAST_DOC_URL +
        '" target="_blank" rel="noopener noreferrer">Fast mode training guide</a> (install, data paths, troubleshooting) · <a href="/lora/sd3.html">Standard Kohya mode</a></p>',
      guide:
        '<div class="anima-fast-guide-collapsible"><button type="button" class="anima-fast-guide-toggle" data-anima-fast-guide-toggle aria-expanded="false"><span class="anima-fast-guide-toggle__icon" aria-hidden="true">▸</span><span class="anima-fast-guide-toggle__label">Dataset paths (differs from Kohya)</span></button><div class="anima-fast-dataset-guide anima-fast-dataset-guide__body" hidden><p>Fast training <strong>reads the resized directory</strong> for bucket-preprocessed images, not the original files directly.</p><ul><li><strong>Training image folder</strong>: originals + captions (e.g. <code>data/xxx/subfolder/</code>)</li><li><strong>Resized folder</strong>: bucket PNGs used for training; <strong>leave empty</strong> to auto-write to <code>.cache/anima_fast/&lt;dataset-path&gt;/resized</code> (reusable for the same dataset)</li></ul><p class="anima-fast-dataset-guide__highlight"><strong>Can both fields use the same path?</strong> Yes. If the folder already has bucket-preprocessed PNGs + captions, both fields can use <strong>the same path</strong>.</p><p class="anima-fast-dataset-guide__note">Output / cache folders are created if missing. Keep cache_latents off on the left unless full preprocess is done.</p></div></div>',
    },
  };

  const ANIMA_FAST_STATUS_ZH_TO_EN = {
    功能已关闭: "Feature disabled",
    插件已就绪: "Plugin ready",
    安装中: "Installing",
    审计中: "Auditing",
    需修复: "Needs repair",
    待审计: "Pending audit",
    "进阶插件 · 待开启": "Advanced plugin · not enabled",
    检查中: "Checking…",
    状态检查失败: "Status check failed",
    安装任务启动中: "Starting install…",
    安装失败: "Install failed",
  };

  const ANIMA_FAST_STATUS_EN_TO_ZH = Object.fromEntries(
    Object.entries(ANIMA_FAST_STATUS_ZH_TO_EN).map(([zh, en]) => [en, zh])
  );

  const EN_TO_ZH = Object.fromEntries(
    Object.entries(ZH_TO_EN).map(([zh, en]) => [en, zh])
  );

  function normalize(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function hasChinese(text) {
    return /[\u4e00-\u9fff]/.test(text || "");
  }

  function resolveI18nLocale() {
    try {
      const globalLoc = window.i18n?.global?.locale;
      if (typeof globalLoc === "string") return globalLoc;
      if (globalLoc && typeof globalLoc.value === "string") return globalLoc.value;
    } catch (e) {
      /* ignore */
    }
    try {
      const app = document.querySelector("#app")?.__vue_app__;
      const i18n = app?.config?.globalProperties?.$i18n;
      const loc = i18n?.locale;
      if (typeof loc === "string") return loc;
      if (loc && typeof loc.value === "string") return loc.value;
      const store = app?.config?.globalProperties?.$store;
      const storeLoc = store?.state?.locale || store?.getters?.locale;
      if (typeof storeLoc === "string") return storeLoc;
    } catch (e) {
      /* ignore */
    }
    return null;
  }

  function inferEnglishFromButtons() {
    const container = document.querySelector(".right-container");
    if (!container) return null;
    const text = container.textContent || "";
    if (/start\s*training|reset\s*all|stop\s*training|copy\s*parameters|load\s*preset/i.test(text)) {
      return true;
    }
    if (/开始训练|全部重置|终止训练|保存参数|加载训练预设/.test(text)) return false;
    return null;
  }

  function inferEnglishFromSchema() {
    const sc = document.querySelector(".schema-container");
    if (!sc) return null;
    const text = sc.textContent || "";
    if (/pretrained|learning rate|dataset directory|train data|model_train_type/i.test(text)) {
      return true;
    }
    if (/预训练模型|数据集目录|学习率设置/.test(text)) return false;
    return null;
  }

  function syncStorageFromI18n() {
    const loc = resolveI18nLocale();
    if (!loc) return;
    sessionStorage.setItem(
      STORAGE_KEY,
      loc.toLowerCase().startsWith("en") ? "en-US" : "zh-CN"
    );
  }

  function detectEnglishUI() {
    const i18nLoc = resolveI18nLocale();
    if (i18nLoc) return i18nLoc.toLowerCase().startsWith("en");

    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored === "en-US") return true;
    if (stored === "zh-CN") return false;

    const buttonGuess = inferEnglishFromButtons();
    if (buttonGuess !== null) return buttonGuess;

    const trainSpan = document.querySelector(
      ".el-button.el-button--primary.is-plain span, .el-button.el-button--primary span"
    );
    const trainText = normalize(trainSpan?.textContent);
    if (/^start\s*training$/i.test(trainText)) return true;
    if (trainText.includes("开始训练")) return false;

    const schemaGuess = inferEnglishFromSchema();
    if (schemaGuess !== null) return schemaGuess;

    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("en")) return true;

    return false;
  }

  function setNodeText(node, text) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const cur = normalize(node.textContent);
    if (!cur) return;
    node.textContent = " " + text + " ";
  }

  function replaceInElement(el, map) {
    if (!el) return;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = normalize(node.textContent);
      if (!raw) continue;
      if (map[raw]) {
        setNodeText(node, map[raw]);
        continue;
      }
      for (const [from, to] of Object.entries(map)) {
        if (raw.includes(from) && from.length > 2) {
          node.textContent = node.textContent.split(from).join(to);
          break;
        }
      }
    }
    el.querySelectorAll("[aria-label]").forEach((a) => {
      const label = normalize(a.getAttribute("aria-label"));
      if (map[label]) a.setAttribute("aria-label", map[label]);
    });
  }

  function applyAnimaFastIntro(english) {
    const wrap = document.querySelector(".anima-fast-intro-wrap");
    if (!wrap) return;

    const marker =
      wrap.querySelector(".anima-fast-credit") ||
      wrap.querySelector(".anima-fast-credit-root");
    const isZh = hasChinese(marker?.textContent || wrap.querySelector("h1")?.textContent);
    if (english && !isZh) return;
    if (!english && isZh) return;

    const b = ANIMA_FAST[english ? "en" : "zh"];
    const h1 = wrap.querySelector("h1");
    if (h1) {
      const anchor = h1.querySelector(".header-anchor");
      h1.textContent = "";
      if (anchor) h1.appendChild(anchor);
      h1.appendChild(document.createTextNode(" " + b.title));
    }

    wrap.querySelectorAll(":scope > p").forEach((p) => {
      if (p.classList.contains("anima-fast-credit") || p.classList.contains("anima-fast-doc-links")) {
        return;
      }
      const raw = normalize(p.textContent);
      if (raw.includes("Kohya") || raw.includes("/lora/sd3.html")) {
        p.textContent = b.kohyaNote;
        return;
      }
      if (!p.closest(".anima-fast-guide-root")) {
        p.textContent = b.intro;
      }
    });

    const creditRoot = wrap.querySelector(".anima-fast-credit-root");
    if (creditRoot) creditRoot.innerHTML = b.credit;
    else {
      const credit = wrap.querySelector(".anima-fast-credit");
      if (credit) credit.outerHTML = b.credit;
    }

    const docRoot = wrap.querySelector(".anima-fast-doc-links-root");
    if (docRoot) docRoot.innerHTML = b.docLinks;
    else {
      const doc = wrap.querySelector(".anima-fast-doc-links");
      if (doc) doc.outerHTML = b.docLinks;
    }

    const open =
      wrap.querySelector(".anima-fast-guide-collapsible.is-open") != null ||
      localStorage.getItem("anima-fast-guide-open") === "1";

    const guideRoot = wrap.querySelector(".anima-fast-guide-root");
    const guideHost = guideRoot || wrap.querySelector(".anima-fast-guide-collapsible");
    if (guideHost) {
      if (guideRoot) {
        guideRoot.innerHTML = b.guide;
      } else {
        guideHost.outerHTML = b.guide;
      }
      const toggle = wrap.querySelector("[data-anima-fast-guide-toggle]");
      const body = wrap.querySelector(".anima-fast-dataset-guide__body");
      const collapsible = wrap.querySelector(".anima-fast-guide-collapsible");
      if (toggle && body && collapsible) {
        body.hidden = !open;
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        collapsible.classList.toggle("is-open", open);
      }
    }
  }

  function applyAnimaFastStatus(english) {
    const status = document.querySelector("[data-anima-fast-status]");
    if (!status) return;
    const raw = normalize(status.textContent);
    if (!raw) return;
    const map = english ? ANIMA_FAST_STATUS_ZH_TO_EN : ANIMA_FAST_STATUS_EN_TO_ZH;
    if (map[raw]) status.textContent = map[raw];
  }

  function applyNavLocale() {
    syncStorageFromI18n();
    const english = detectEnglishUI();
    document.documentElement.dataset.sdUiLocale = english ? "en-US" : "zh-CN";
    sessionStorage.setItem(STORAGE_KEY, english ? "en-US" : "zh-CN");

    const map = english ? ZH_TO_EN : EN_TO_ZH;
    const sidebar = document.querySelector(".sidebar");
    if (sidebar) replaceInElement(sidebar, map);

    const hub = document.querySelector(".sd-home-hub");
    if (hub) replaceInElement(hub, map);

    applyAnimaFastIntro(english);

    const main = document.querySelector(".right-container .theme-default-content main");
    if (main) replaceInElement(main, map);

    applyAnimaFastIntro(english);

    const rightHeader = document.querySelector(".right-container section > header");
    if (rightHeader) replaceInElement(rightHeader, map);

    const buttons = document.querySelector(".right-container .el-row");
    if (buttons) replaceInElement(buttons.closest(".right-container") || buttons, map);

    applyAnimaFastStatus(english);

    const installBtn = document.querySelector("[data-anima-fast-install] span");
    if (installBtn) {
      const t = normalize(installBtn.textContent);
      if (english && (t === "开启插件" || t === "Enable plugin")) {
        installBtn.textContent = "Enable plugin";
      } else if (!english && (t === "开启插件" || t === "Enable plugin")) {
        installBtn.textContent = "开启插件";
      }
    }

    const tagline = document.querySelector(".sd-anima-finetune-tagline");
    if (tagline && english) {
      tagline.textContent = "anima-finetune — anything is possible";
    } else if (tagline && !english) {
      tagline.textContent = "anima-finetune ，一切皆有可能";
    }
  }

  function afterLocaleChange() {
    const syncLater = () => {
      syncStorageFromI18n();
      applyNavLocale();
    };
    syncLater();
    setTimeout(syncLater, 60);
    setTimeout(syncLater, 220);
    setTimeout(syncLater, 500);
    setTimeout(syncLater, 1200);
    requestAnimationFrame(syncLater);
  }

  function hookLanguageToggle() {
    const bottom = document.querySelector(".sidebar-bottom");
    if (bottom && !bottom.dataset.sdNavI18nHooked) {
      bottom.dataset.sdNavI18nHooked = "1";
      bottom.addEventListener(
        "click",
        (ev) => {
          const btn = ev.target.closest("button");
          if (!btn) return;
          const row = btn.closest("li.appearance");
          if (!row || !/language/i.test(row.textContent || "")) return;
          afterLocaleChange();
        },
        true
      );
    }

    if (!document.documentElement.dataset.sdNavI18nDocHooked) {
      document.documentElement.dataset.sdNavI18nDocHooked = "1";
      document.addEventListener(
        "click",
        (ev) => {
          const btn = ev.target.closest("button");
          if (!btn) return;
          const label = normalize(btn.textContent);
          if (/^(switch language:\s*)?(en-us|zh-cn)$/i.test(label)) {
            sessionStorage.setItem(
              STORAGE_KEY,
              /en-us/i.test(label) ? "en-US" : "zh-CN"
            );
            afterLocaleChange();
          }
        },
        true
      );
    }
  }

  function watchGlobalI18n() {
    if (window.__sdNavI18nWatch) return;
    window.__sdNavI18nWatch = true;
    let last = null;
    const tick = () => {
      const loc = resolveI18nLocale();
      if (loc && loc !== last) {
        last = loc;
        afterLocaleChange();
      }
    };
    setInterval(tick, 400);
    setTimeout(tick, 0);
    setTimeout(tick, 800);
  }

  let scheduled = null;
  function scheduleApply() {
    if (scheduled) clearTimeout(scheduled);
    scheduled = setTimeout(() => {
      scheduled = null;
      applyNavLocale();
      hookLanguageToggle();
    }, 60);
  }

  function boot() {
    applyNavLocale();
    hookLanguageToggle();
    watchGlobalI18n();

    const root = document.querySelector("#app");
    if (root) {
      new MutationObserver(scheduleApply).observe(root, {
        childList: true,
        subtree: true,
      });
    }
    window.addEventListener("hashchange", scheduleApply);
    window.addEventListener("popstate", scheduleApply);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
