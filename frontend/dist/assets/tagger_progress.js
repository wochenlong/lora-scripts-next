(function () {
  "use strict";

  var startBtn = null;
  var startLabel = "启动";
  var pollTimer = null;
  var hideTimer = null;
  var jobPending = false;

  function getEls() {
    var zone = document.getElementById("tagger-run-zone");
    if (!zone) return null;
    return {
      zone: zone,
      barFill: zone.querySelector(".tagger-run-zone__bar-fill"),
      textEl: zone.querySelector(".tagger-run-zone__text"),
    };
  }

  function isTaggerPage() {
    return !!document.getElementById("tagger-run-zone");
  }

  function findStartButton() {
    var zone = document.getElementById("tagger-run-zone");
    if (!zone || !zone.parentElement) return null;
    var buttons = zone.parentElement.querySelectorAll(".el-button");
    for (var i = 0; i < buttons.length; i++) {
      var span = buttons[i].querySelector("span");
      var label = (span ? span.textContent : buttons[i].textContent).trim();
      if (label === "启动") return buttons[i];
    }
    return null;
  }

  function showZone(els) {
    els.zone.classList.add("is-active");
  }

  function hideZone(els) {
    els.zone.classList.remove("is-active");
  }

  function setButtonBusy(busy) {
    if (!startBtn) startBtn = findStartButton();
    if (!startBtn) return;
    startBtn.disabled = !!busy;
    startBtn.setAttribute("aria-disabled", busy ? "true" : "false");
    var span = startBtn.querySelector("span");
    var target = span || startBtn;
    target.textContent = busy ? "处理中…" : startLabel;
  }

  function applySnapshot(els, data) {
    var phase = data.phase || "idle";
    var pct = data.percent;
    var indeterminate =
      pct == null && (phase === "download" || phase === "preparing");

    els.barFill.classList.toggle("is-indeterminate", indeterminate);
    if (indeterminate) {
      els.barFill.style.width = "";
    } else {
      els.barFill.style.width = Math.max(0, Math.min(100, pct || 0)) + "%";
    }

    var line = data.message || "";
    if (phase === "tagging" && data.label) {
      line = (data.message || "") + " · " + data.label;
    }
    els.textEl.textContent = line;
    showZone(els);
  }

  function stopPoll(hide) {
    jobPending = false;
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    setButtonBusy(false);
    var els = getEls();
    if (!els) return;
    if (hide) {
      hideZone(els);
      els.barFill.classList.remove("is-indeterminate");
      els.barFill.style.width = "0%";
      els.textEl.textContent = "";
    }
  }

  async function pollOnce() {
    var els = getEls();
    if (!els) return;
    try {
      var res = await fetch("/api/tagger/status");
      if (!res.ok) return;
      var body = await res.json();
      var data = body.data || body;
      if (!data.active && data.phase === "idle") {
        if (jobPending) return;
        stopPoll(true);
        return;
      }
      jobPending = false;
      applySnapshot(els, data);
      if (data.phase === "done" || data.phase === "error") {
        if (!hideTimer) {
          hideTimer = setTimeout(function () {
            stopPoll(true);
          }, 2000);
        }
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    } catch (e) {
      /* keep polling */
    }
  }

  function beginJobUI() {
    var els = getEls();
    if (!els) return;
    startBtn = findStartButton();
    if (startBtn) {
      var span = startBtn.querySelector("span");
      startLabel = (span ? span.textContent : startBtn.textContent).trim() || "启动";
    }
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    jobPending = true;
    showZone(els);
    els.textEl.textContent = "准备中…";
    els.barFill.classList.add("is-indeterminate");
    els.barFill.style.width = "";
    setButtonBusy(true);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollOnce, 400);
    pollOnce();
  }

  function requestUrl(input) {
    if (typeof input === "string") return input;
    if (input && input.url) return input.url;
    return "";
  }

  function requestMethod(input, init) {
    if (init && init.method) return init.method.toUpperCase();
    if (input && input.method) return input.method.toUpperCase();
    return "GET";
  }

  function isInterrogatePost(url, method) {
    return method === "POST" && url.indexOf("/api/interrogate") >= 0;
  }

  var origFetch = window.fetch;
  if (typeof origFetch === "function") {
    window.fetch = function (input, init) {
      var url = requestUrl(input);
      var method = requestMethod(input, init);
      if (isInterrogatePost(url, method)) beginJobUI();
      return origFetch.apply(this, arguments);
    };
  }

  document.addEventListener(
    "click",
    function (ev) {
      if (!isTaggerPage()) return;
      var btn = ev.target && ev.target.closest ? ev.target.closest(".el-button") : null;
      if (!btn || !document.getElementById("tagger-run-zone")) return;
      if (!btn.parentElement || !btn.parentElement.contains(document.getElementById("tagger-run-zone"))) return;
      if ((btn.textContent || "").trim() === "启动") beginJobUI();
    },
    true
  );
})();
