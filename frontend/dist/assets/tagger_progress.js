(function () {
  "use strict";

  var zone = document.createElement("div");
  zone.className = "tagger-run-zone";
  zone.setAttribute("aria-live", "polite");
  zone.innerHTML =
    '<div class="tagger-run-zone__bar" role="progressbar" aria-valuemin="0" aria-valuemax="100">' +
    '<div class="tagger-run-zone__bar-fill"></div></div>' +
    '<p class="tagger-run-zone__text"></p>';

  var barFill = zone.querySelector(".tagger-run-zone__bar-fill");
  var textEl = zone.querySelector(".tagger-run-zone__text");
  var startBtn = null;
  var startLabel = "启动";
  var pollTimer = null;
  var hideTimer = null;
  var jobPending = false;
  var mounted = false;

  function isTaggerPage() {
    var path = (location.pathname || "").toLowerCase();
    if (/\/tagger(?:\.html|\.md)?$/i.test(path)) return true;
    var h1 = document.querySelector(".right-container h1, .example-container h1");
    if (h1 && /tagger/i.test(h1.textContent)) return true;
    var form = document.querySelector(".schema-container form");
    if (!form) return false;
    return (form.textContent || "").indexOf("interrogator_model") >= 0;
  }

  function findStartButton() {
    var right = document.querySelector(".example-container .right-container");
    if (!right) return null;
    var buttons = right.querySelectorAll(".el-button");
    for (var i = 0; i < buttons.length; i++) {
      var span = buttons[i].querySelector("span");
      var label = (span ? span.textContent : buttons[i].textContent).trim();
      if (label === "启动") return buttons[i];
    }
    return null;
  }

  function showZone() {
    zone.removeAttribute("hidden");
    zone.style.display = "block";
  }

  function hideZone() {
    zone.setAttribute("hidden", "hidden");
    zone.style.display = "none";
  }

  function setButtonBusy(busy) {
    if (!startBtn) return;
    startBtn.disabled = !!busy;
    startBtn.setAttribute("aria-disabled", busy ? "true" : "false");
    var span = startBtn.querySelector("span");
    var target = span || startBtn;
    target.textContent = busy ? "处理中…" : startLabel;
  }

  function applySnapshot(data) {
    var phase = data.phase || "idle";
    var pct = data.percent;
    var indeterminate =
      pct == null && (phase === "download" || phase === "preparing");

    barFill.classList.toggle("is-indeterminate", indeterminate);
    if (indeterminate) {
      barFill.style.width = "";
    } else {
      barFill.style.width = Math.max(0, Math.min(100, pct || 0)) + "%";
    }

    var line = data.message || "";
    if (phase === "tagging" && data.label) {
      line = (data.message || "") + " · " + data.label;
    }
    textEl.textContent = line;
    showZone();
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
    if (hide) {
      hideZone();
      barFill.classList.remove("is-indeterminate");
      barFill.style.width = "0%";
      textEl.textContent = "";
    }
  }

  async function pollOnce() {
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
      applySnapshot(data);
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
    if (!isTaggerPage()) return;
    mountZone();
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    jobPending = true;
    showZone();
    textEl.textContent = "准备中…";
    barFill.classList.add("is-indeterminate");
    barFill.style.width = "";
    setButtonBusy(true);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollOnce, 400);
    pollOnce();
  }

  function mountZone() {
    if (!isTaggerPage()) return false;
    var btn = findStartButton();
    if (!btn || !btn.parentElement) return false;
    startBtn = btn;
    if (!zone.isConnected) {
      btn.parentElement.insertBefore(zone, btn);
      mounted = true;
    }
    if (!btn.dataset.taggerProgressBound) {
      btn.dataset.taggerProgressBound = "1";
      var span = btn.querySelector("span");
      startLabel = (span ? span.textContent : btn.textContent).trim() || "启动";
    }
    return true;
  }

  function teardown() {
    if (zone.isConnected) zone.remove();
    mounted = false;
    startBtn = null;
    stopPoll(true);
  }

  function tick() {
    if (!isTaggerPage()) {
      if (mounted) teardown();
      return;
    }
    mountZone();
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

  var OrigXHR = window.XMLHttpRequest;
  if (typeof OrigXHR === "function") {
    window.XMLHttpRequest = function () {
      var xhr = new OrigXHR();
      var origOpen = xhr.open;
      var origSend = xhr.send;
      xhr.open = function (method, url) {
        xhr.__taggerMethod = (method || "GET").toUpperCase();
        xhr.__taggerUrl = url || "";
        return origOpen.apply(xhr, arguments);
      };
      xhr.send = function () {
        if (isInterrogatePost(xhr.__taggerUrl || "", xhr.__taggerMethod || "GET")) {
          beginJobUI();
        }
        return origSend.apply(xhr, arguments);
      };
      return xhr;
    };
  }

  document.addEventListener(
    "click",
    function (ev) {
      if (!isTaggerPage()) return;
      var btn = ev.target && ev.target.closest ? ev.target.closest(".el-button") : null;
      if (!btn || !btn.closest(".right-container")) return;
      var label = (btn.textContent || "").trim();
      if (label === "启动") beginJobUI();
    },
    true
  );

  hideZone();
  tick();
  setInterval(tick, 500);
})();
