/**
 * Version chip next to the "Next Trainer" sidebar title (reads /api/version).
 */
(function () {
  const VERSION_URL = "/api/version";
  const CHIP_ID = "sd-brand-version-chip";
  const BRAND_TITLE = "Next Trainer";
  const GAP_PX = 6;
  const OFFSET_Y_PX = 3;

  async function fetchVersion() {
    try {
      const res = await fetch(VERSION_URL);
      const json = await res.json();
      if (json && json.status === "success" && json.data && json.data.version) {
        return String(json.data.version).trim();
      }
    } catch (e) {
      /* backend offline */
    }
    return null;
  }

  function findBrandLink() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return null;
    return (
      sidebar.querySelector("li:first-child > a.sidebar-item.sidebar-heading[href='/']") ||
      sidebar.querySelector('a.sidebar-item.sidebar-heading[aria-label="Next Trainer"]')
    );
  }

  function measureBrandTitleRect(link) {
    const walker = document.createTreeWalker(link, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = node.textContent || "";
      const idx = raw.indexOf(BRAND_TITLE);
      if (idx !== -1) {
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + BRAND_TITLE.length);
        const r = range.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) return r;
      }
    }
    return link.getBoundingClientRect();
  }

  function positionChip() {
    const chip = document.getElementById(CHIP_ID);
    const link = findBrandLink();
    if (!chip || !link) {
      if (chip) chip.style.visibility = "hidden";
      return false;
    }

    const linkRect = link.getBoundingClientRect();
    const titleRect = measureBrandTitleRect(link);
    if (linkRect.width <= 0 || linkRect.height <= 0) {
      chip.style.visibility = "hidden";
      return false;
    }

    chip.style.visibility = "visible";
    const anchor = titleRect.height > 0 ? titleRect : linkRect;
    chip.style.top =
      Math.round(anchor.top + (anchor.height - chip.offsetHeight) / 2 + OFFSET_Y_PX) + "px";
    chip.style.left = Math.round(titleRect.right + GAP_PX) + "px";
    chip.style.right = "auto";
    return true;
  }

  function ensureChip(version) {
    if (!version) return;
    document.documentElement.dataset.sdTrainerVersion = version;

    let chip = document.getElementById(CHIP_ID);
    if (!chip) {
      chip = document.createElement("div");
      chip.id = CHIP_ID;
      chip.className = "sd-brand-version-chip";
      chip.setAttribute("title", "Next Trainer / SD-Trainer 版本号");
      document.body.appendChild(chip);
    }
    chip.textContent = "v" + version;
    positionChip();
  }

  let resizeTimer = null;
  function scheduleReposition() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(positionChip, 80);
  }

  async function boot() {
    const version = await fetchVersion();
    if (!version) return;
    ensureChip(version);

    let tries = 0;
    const retry = setInterval(function () {
      positionChip();
      if (++tries >= 30) clearInterval(retry);
    }, 200);

    window.addEventListener("resize", scheduleReposition);
    window.addEventListener("scroll", scheduleReposition, true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
