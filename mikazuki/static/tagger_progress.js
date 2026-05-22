(function () {
  if (!/\/tagger(?:\.html)?$/i.test(location.pathname)) return;

  var zone = document.createElement("div");
  zone.className = "tagger-run-zone";
  zone.hidden = true;
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

  function mountZone() {
    var btn = findStartButton();
    if (!btn) return false;
    startBtn = btn;
    if (!zone.isConnected) {
      btn.parentElement.insertBefore(zone, btn);
    }
    if (!btn.dataset.taggerProgressBound) {
      btn.dataset.taggerProgressBound = "1";
      var span = btn.querySelector("span");
      startLabel = (span ? span.textContent : btn.textContent).trim() || "启动";
      btn.addEventListener("click", onStartClick);
    }
    return true;
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
    var indeterminate = pct == null && (phase === "download" || phase === "preparing");

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
    zone.hidden = false;
  }

  function stopPoll(hideZone) {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    setButtonBusy(false);
    if (hideZone) {
      zone.hidden = true;
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
        stopPoll(true);
        return;
      }
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
      /* keep polling; request may fail briefly while server starts job */
    }
  }

  function onStartClick() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    zone.hidden = false;
    textEl.textContent = "准备中…";
    barFill.classList.add("is-indeterminate");
    barFill.style.width = "";
    setButtonBusy(true);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollOnce, 400);
    pollOnce();
  }

  mountZone();
  setInterval(mountZone, 800);
})();
