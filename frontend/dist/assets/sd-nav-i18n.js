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
    if (htmlLang.startsWith("en")) return true;
    if (htmlLang.startsWith("zh")) return false;

    const trainSpan = document.querySelector(
      ".el-button.el-button--primary.is-plain span, .el-button.el-button--primary span"
    );
    const trainText = normalize(trainSpan?.textContent);
    if (/^start\s*training$/i.test(trainText)) return true;
    if (trainText.includes("开始训练")) return false;

    return true;
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
      hookLanguageToggle();
    }, 60);
  }

  function boot() {
    applyNavLocale();
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
