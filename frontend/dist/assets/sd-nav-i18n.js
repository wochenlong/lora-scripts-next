/**
 * Sidebar / home hub locale labels when UI is English (en-US).
 * Schema forms use vue-i18n; VuePress sidebar SSR text stays Chinese without this patch.
 */
(function () {
  const STORAGE_KEY = "sd-trainer-ui-locale";
  const ADVANCED_LINKS_KEY = "sd-trainer-ui-advanced-links";
  const DEFAULT_ADVANCED_LINKS = {
    showTensorboard: false,
    showLegacyTagEditor: false,
  };

  const ZH_TO_EN = {
    训练: "Training",
    "LoRA训练": "LoRA Training",
    "LoRA 训练": "LoRA Training",
    全量微调: "Full Finetune",
    工具与调试: "Tools",
    数据集打标: "Dataset Tagging",
    经典标签编辑: "Legacy Tag Editor",
    原生标签编辑: "Native Tag Editor",
    标签编辑: "Tag Editor",
    "LoRA 脚本工具": "LoRA Scripts",
    帮助: "Help",
    新手上路: "Getting Started",
    训练参数说明: "Training Parameters",
    其他: "More",
    "UI 设置": "Settings",
    设置: "Settings",
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
  };

  const EN_TO_ZH = Object.fromEntries(
    Object.entries(ZH_TO_EN).map(([zh, en]) => [en, zh])
  );

  function normalize(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function resolveI18nLocale() {
    try {
      const app = document.querySelector("#app")?.__vue_app__;
      const i18n = app?.config?.globalProperties?.$i18n;
      const loc = i18n?.locale;
      if (typeof loc === "string") return loc;
      if (loc && typeof loc.value === "string") return loc.value;
    } catch (e) {
      /* ignore */
    }
    return null;
  }

  function detectEnglishUI() {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored === "en-US") return true;
    if (stored === "zh-CN") return false;

    const i18nLoc = resolveI18nLocale();
    if (i18nLoc) return i18nLoc.toLowerCase().startsWith("en");

    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("zh")) return false;

    const trainSpan = document.querySelector(
      ".el-button.el-button--primary.is-plain span, .el-button.el-button--primary span"
    );
    const trainText = normalize(trainSpan?.textContent);
    if (/^start\s*training$/i.test(trainText)) return true;
    if (trainText.includes("开始训练")) return false;

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

  function applyNavLocale() {
    const english = detectEnglishUI();
    document.documentElement.dataset.sdUiLocale = english ? "en-US" : "zh-CN";

    const map = english ? ZH_TO_EN : EN_TO_ZH;
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (sidebar) replaceInElement(sidebar, map);

    const hub = document.querySelector(".sd-home-hub");
    if (hub) replaceInElement(hub, map);

    const main = document.querySelector(".right-container .theme-default-content main");
    if (main) replaceInElement(main, map);

    const rightHeader = document.querySelector(".right-container section > header");
    if (rightHeader) replaceInElement(rightHeader, map);

    const buttons = document.querySelector(".right-container .el-row");
    if (buttons) replaceInElement(buttons.closest(".right-container") || buttons, map);

    const tagline = document.querySelector(".sd-anima-finetune-tagline");
    if (tagline && english) {
      tagline.textContent = "anima-finetune — anything is possible";
    } else if (tagline && !english) {
      tagline.textContent = "anima-finetune ，一切皆有可能";
    }
  }

  function ensureStableSidebarState() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return;
    const groups = Array.from(sidebar.children || []);
    for (const li of groups) {
      const heading = normalize(li.querySelector(":scope > p.sidebar-item.sidebar-heading")?.textContent);
      if (heading !== "训练" && heading !== "Training") continue;
      const ul = li.querySelector(":scope > ul.sidebar-item-children");
      if (!ul) continue;
      ul.style.display = "";
      li.dataset.sdForceExpanded = "1";
    }
  }

  function readAdvancedLinks() {
    try {
      return {
        ...DEFAULT_ADVANCED_LINKS,
        ...(JSON.parse(localStorage.getItem(ADVANCED_LINKS_KEY) || "{}") || {}),
      };
    } catch (e) {
      return { ...DEFAULT_ADVANCED_LINKS };
    }
  }

  function writeAdvancedLinks(next) {
    localStorage.setItem(ADVANCED_LINKS_KEY, JSON.stringify({
      ...DEFAULT_ADVANCED_LINKS,
      ...next,
    }));
  }

  function setSidebarLinkVisible(selector, visible) {
    const link = document.querySelector(`.sidebar .sidebar-items ${selector}`);
    const item = link?.closest("li");
    if (!item) return;
    item.hidden = !visible;
    item.style.display = visible ? "" : "none";
  }

  function applyAdvancedLinkVisibility() {
    const flags = readAdvancedLinks();
    setSidebarLinkVisible('a[href="/tensorboard.md"]', !!flags.showTensorboard);
    setSidebarLinkVisible('a[href="/tageditor.md"]', !!flags.showLegacyTagEditor);
  }

  function maskSettingsOutput() {
    if (!location.pathname.endsWith("/other/settings.html")) return;
    const output = document.querySelector("#test-output1");
    if (output) {
      output.hidden = true;
      output.style.display = "none";
    }
    document.querySelectorAll("h1, h2.k-schema-header, a.sidebar-item").forEach((el) => {
      const text = normalize(el.textContent);
      if (text === "训练 UI 设置" || text === "UI 设置" || text === "UI Settings") {
        if (el.matches("h1, h2.k-schema-header")) {
          el.textContent = "设置";
        } else {
          el.childNodes.forEach((node) => {
            if (node.nodeType === Node.TEXT_NODE && normalize(node.textContent)) {
              node.textContent = " 设置 ";
            }
          });
        }
        el.setAttribute?.("aria-label", "设置");
      }
    });
    document.title = document.title
      .replace("训练 UI 设置", "设置")
      .replace("UI 设置", "设置")
      .replace("UI Settings", "Settings");
  }

  const SETTINGS_HELP = {
    tensorboard_url: {
      title: "Tensorboard 地址",
      body: "用于打开训练日志的 Tensorboard 页面。这个入口默认隐藏，需要时可以在下方旧功能入口里打开。",
    },
    dataset_tagger_api_endpoint: {
      title: "标签编辑器 API 打标地址",
      body: "填写兼容 OpenAI 风格的接口根地址，例如 https://api.openai.com/v1。本地或第三方 VLM 服务也可以放在这里。",
    },
    dataset_tagger_api_key: {
      title: "标签编辑器 API Key",
      body: "敏感信息，只用于请求 API 打标服务。输入框会打码显示，右侧预览不会展示明文。",
    },
    dataset_tagger_api_model: {
      title: "标签编辑器 API 模型",
      body: "用于自然语言 caption 的模型名称。不同 API 服务可能使用不同模型 id。",
    },
    dataset_tagger_api_prompt: {
      title: "标签编辑器 API 提示词",
      body: "发送给自然语言模型的 caption 指令。建议要求输出简洁 caption，不要 Markdown 或解释。",
    },
    advanced_links: {
      title: "隐藏旧功能入口",
      body: "Tensorboard 和经典标签编辑默认隐藏，避免用户优先进入旧页面。需要排查问题时可以临时显示。",
    },
  };

  function findSettingItem(name) {
    return Array.from(document.querySelectorAll(".schema-container .k-schema-item")).find((item) =>
      normalize(item.textContent).includes(name)
    );
  }

  function maskSensitiveSettingsFields() {
    if (!location.pathname.endsWith("/other/settings.html")) return;
    const keyItem = findSettingItem("dataset_tagger_api_key");
    const input = keyItem?.querySelector("input");
    if (!input) return;
    input.type = "password";
    input.autocomplete = "new-password";
    input.setAttribute("spellcheck", "false");
    input.setAttribute("aria-label", "标签编辑器 API Key，已打码");
  }

  function renderSettingsHelp(activeKey = "dataset_tagger_api_endpoint") {
    if (!location.pathname.endsWith("/other/settings.html")) return;
    const container = document.querySelector(".right-container .theme-default-content main");
    if (!container) return;
    const help = SETTINGS_HELP[activeKey] || SETTINGS_HELP.dataset_tagger_api_endpoint;
    container.innerHTML = `
      <section class="sd-settings-help" style="max-width:520px;padding:8px 0 0;">
        <p style="margin:0 0 8px;color:var(--c-brand);font-weight:700;">当前选项说明</p>
        <h1 style="margin:0 0 14px;font-size:24px;line-height:1.35;">${help.title}</h1>
        <p style="margin:0;color:var(--c-text-lighter);font-size:14px;line-height:1.9;">${help.body}</p>
      </section>`;
  }

  function hookSettingsHelp() {
    if (!location.pathname.endsWith("/other/settings.html")) return;
    const pairs = [
      ["tensorboard_url", "tensorboard_url"],
      ["dataset_tagger_api_endpoint", "dataset_tagger_api_endpoint"],
      ["dataset_tagger_api_key", "dataset_tagger_api_key"],
      ["dataset_tagger_api_model", "dataset_tagger_api_model"],
      ["dataset_tagger_api_prompt", "dataset_tagger_api_prompt"],
    ];
    for (const [needle, key] of pairs) {
      const item = findSettingItem(needle);
      if (!item || item.dataset.sdHelpHooked) continue;
      item.dataset.sdHelpHooked = "1";
      item.addEventListener("mouseenter", () => renderSettingsHelp(key));
      item.addEventListener("focusin", () => renderSettingsHelp(key));
      item.addEventListener("click", () => renderSettingsHelp(key));
    }
    const advanced = document.getElementById("sd-advanced-link-settings");
    if (advanced && !advanced.dataset.sdHelpHooked) {
      advanced.dataset.sdHelpHooked = "1";
      advanced.addEventListener("mouseenter", () => renderSettingsHelp("advanced_links"));
      advanced.addEventListener("focusin", () => renderSettingsHelp("advanced_links"));
      advanced.addEventListener("click", () => renderSettingsHelp("advanced_links"));
    }
    renderSettingsHelp();
  }

  function injectAdvancedSettingsPanel() {
    if (!location.pathname.endsWith("/other/settings.html")) return;
    if (document.getElementById("sd-advanced-link-settings")) return;
    const form = document.querySelector(".schema-container form");
    if (!form) return;
    const flags = readAdvancedLinks();
    const panel = document.createElement("section");
    panel.id = "sd-advanced-link-settings";
    panel.className = "k-schema-item";
    panel.innerHTML = `
      <div class="actions"></div>
      <div class="k-schema-main">
        <div class="k-schema-left">
          <h3><span>隐藏旧功能入口</span></h3>
          <div class="markdown"><p>Tensorboard 和经典标签编辑默认从侧边栏隐藏，需要时可临时显示。</p></div>
        </div>
        <div class="k-schema-right">
          <label style="display:flex;align-items:center;gap:8px;margin:4px 0;">
            <input id="sd-show-tensorboard" type="checkbox">
            <span>显示 Tensorboard 入口</span>
          </label>
          <label style="display:flex;align-items:center;gap:8px;margin:4px 0;">
            <input id="sd-show-legacy-tageditor" type="checkbox">
            <span>显示经典标签编辑入口</span>
          </label>
        </div>
      </div>`;
    form.appendChild(panel);
    const tensorboard = panel.querySelector("#sd-show-tensorboard");
    const legacy = panel.querySelector("#sd-show-legacy-tageditor");
    tensorboard.checked = !!flags.showTensorboard;
    legacy.checked = !!flags.showLegacyTagEditor;
    const save = () => {
      writeAdvancedLinks({
        showTensorboard: tensorboard.checked,
        showLegacyTagEditor: legacy.checked,
      });
      applyAdvancedLinkVisibility();
    };
    tensorboard.addEventListener("change", save);
    legacy.addEventListener("change", save);
  }

  function hookLanguageToggle() {
    const bottom = document.querySelector(".sidebar-bottom");
    if (!bottom || bottom.dataset.sdNavI18nHooked) return;
    bottom.dataset.sdNavI18nHooked = "1";
    bottom.addEventListener(
      "click",
      (ev) => {
        const btn = ev.target.closest("button");
        if (!btn) return;
        const row = btn.closest("li.appearance");
        if (!row || !/language/i.test(row.textContent || "")) return;
        const next = detectEnglishUI() ? "zh-CN" : "en-US";
        sessionStorage.setItem(STORAGE_KEY, next);
        setTimeout(applyNavLocale, 80);
        setTimeout(applyNavLocale, 400);
      },
      true
    );
  }

  let scheduled = null;
  function scheduleApply() {
    if (scheduled) clearTimeout(scheduled);
    scheduled = setTimeout(() => {
      scheduled = null;
      applyNavLocale();
      ensureStableSidebarState();
      applyAdvancedLinkVisibility();
      maskSettingsOutput();
      injectAdvancedSettingsPanel();
      maskSensitiveSettingsFields();
      hookSettingsHelp();
      hookLanguageToggle();
    }, 60);
  }

  function boot() {
    applyNavLocale();
    ensureStableSidebarState();
    applyAdvancedLinkVisibility();
    maskSettingsOutput();
    injectAdvancedSettingsPanel();
    maskSensitiveSettingsFields();
    hookSettingsHelp();
    hookLanguageToggle();

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


