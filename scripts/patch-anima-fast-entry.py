#!/usr/bin/env python3
"""Register the Anima Fast trainer entry in the built VuePress frontend."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from spa_asset_cache import SPA_ASSET_CACHE_KEY

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"
ASSETS = DIST / "assets"
APP_JS = ASSETS / "app.547295de.js"
APP_JS_CACHE_KEY = SPA_ASSET_CACHE_KEY
APP_JS_MODULE = f"./app.547295de.js?v={APP_JS_CACHE_KEY}"

SOURCE_HTML = DIST / "lora/sd3.html"
TARGET_HTML = DIST / "lora/anima-fast.html"
PAGE_JS = ASSETS / "anima-fast.html.page.js"
DATA_JS = ASSETS / "anima-fast.html.data.js"

POLISH_CSS = ASSETS / "sd-trainer-ui-polish.css"
STYLE_CSS = ASSETS / "style.874872ce.css"
INSTALL_JS = ASSETS / "anima-fast-install.js"

ROUTE_KEY = "v-anima-fast"
PAGE_TITLE = "Anima LoRA · Fast 模式"
TRAIN_TYPE = "anima-lora-fast"
GUIDE_CSS_MARKER = "anima-fast-dataset-guide"
CREDIT_CSS_MARKER = "anima-fast-credit"

GUARD_PATTERN = re.compile(
    r";?\(\(\)=>\{if\(window\.__ANIMA_FAST_INSTALL_GUARD__\).*?setTimeout\(status,0\)\}\)\(\);",
    re.DOTALL,
)

FAST_PAGE_INTRO = (
    "Anima 高速 LoRA 训练（进阶插件）。需单独安装 runtime，仅支持标准 LoRA。"
    "显存建议 16GB+，首次安装需下载数 GB 依赖。"
)

FAST_CREDIT_HTML = (
    '<p class="anima-fast-credit">'
    '引擎：<a href="https://github.com/sorryhyun/anima_lora" target="_blank" rel="noopener noreferrer">'
    "sorryhyun/anima_lora</a>"
    "</p>"
)

FAST_GUIDE_LINK_HTML = (
    '<p class="anima-fast-guide-link">'
    '说明与数据路径详见 '
    '<a href="/help/guide.html#anima-fast-lora" data-guide-fast-link>新手上路 → Anima Fast</a>'
    "</p>"
)

FAST_DOC_URL = "https://github.com/wochenlong/lora-scripts-next/blob/main/docs/anima-fast.md"

FAST_DOC_LINKS_HTML = (
    '<p class="anima-fast-doc-links">'
    f'<a href="{FAST_DOC_URL}" target="_blank" rel="noopener noreferrer">'
    "Fast 模式训练教程</a>（安装、数据路径、故障排除）"
    ' · <a href="/lora/sd3.html">标准 Kohya 模式</a>'
    ' · <a href="/lora/anima-fast.html"><strong>前往 Fast 训练页</strong></a>'
    "</p>"
)

FAST_DATASET_GUIDE_BODY = """
  <p>Fast 训练<strong>实际读取 resized 目录</strong>里的 bucket 预处理图，不是直接读原图。</p>
  <ul>
    <li><strong>训练图片目录</strong>：原图 + caption（如 <code>data/xxx/子文件夹/</code>）</li>
    <li><strong>resized 目录</strong>：训练真正用到的 bucket PNG；<strong>留空</strong>时自动写入 <code>.cache/anima_fast/&lt;数据集路径&gt;/resized</code>（同一数据集可复用）</li>
  </ul>
  <p class="anima-fast-dataset-guide__highlight"><strong>可以填同一路径吗？</strong>可以。若该目录已是 bucket 预处理后的 PNG + caption，两处可填<strong>相同路径</strong>。</p>
  <p class="anima-fast-dataset-guide__note">输出 / cache 目录不存在时会自动创建。左侧「cache_latents」等保持关闭，除非已完成完整 preprocess。</p>
""".strip()

FAST_DATASET_GUIDE_HTML = f"""
<div class="anima-fast-guide-collapsible">
  <button type="button" class="anima-fast-guide-toggle" data-anima-fast-guide-toggle aria-expanded="false">
    <span class="anima-fast-guide-toggle__icon" aria-hidden="true">▸</span>
    <span class="anima-fast-guide-toggle__label">数据集路径说明（与 Kohya 不同）</span>
  </button>
  <div class="anima-fast-dataset-guide anima-fast-dataset-guide__body" hidden>
    {FAST_DATASET_GUIDE_BODY}
  </div>
</div>
""".strip()


GUIDE_PAGER_CSS_MARKER = "/* ----- Guide pager ----- */"


def build_fast_guide_section_html(*, compact: bool = False) -> str:
    body = FAST_DATASET_GUIDE_BODY
    if compact:
        body = re.sub(r"\s+", " ", body.strip())
    return (
        '<section class="sd-guide-anima-fast">'
        '<h2 id="anima-fast-lora" tabindex="-1">'
        '<a class="header-anchor" href="#anima-fast-lora" aria-hidden="true">#</a> '
        "Anima LoRA · Fast 模式</h2>"
        f"<p>{FAST_PAGE_INTRO}</p>"
        f"{FAST_DOC_LINKS_HTML}"
        f'<div class="anima-fast-dataset-guide anima-fast-dataset-guide__body">{body}</div>'
        "</section>"
    )


GUIDE_INTRO_INNER = (
    '<div class="sd-guide-intro sd-guide-intro--text-only">'
    '<div class="sd-guide-intro__body">'
    '<h2 id="新手上路" tabindex="-1">'
    '<a class="header-anchor" href="#新手上路" aria-hidden="true">#</a> 新手上路</h2>'
    "<ol>"
    "<li><strong>准备数据</strong>：训练图片 + 同名 <code>.txt</code> 标签；可用「工具与调试 → 数据集打标」。</li>"
    "<li><strong>选择训练类型</strong>（侧栏「训练」）："
    "<ul>"
    "<li><strong>LoRA 训练</strong><ul>"
    '<li><a href="/lora/sd3.html">Anima LoRA</a> — Anima DiT（推荐）</li>'
    '<li><a href="/lora/anima-fast.html">Anima Fast</a> — 可选插件加速（进阶，页内安装）</li>'
    '<li><a href="/lora/flux.html">Flux</a></li>'
    '<li><a href="/lora/master.html">Stable Diffusion</a> — SD1.5 / SDXL LoRA</li>'
    "</ul></li>"
    "<li><strong>全量微调</strong><ul>"
    '<li><a href="/lora/anima-finetune.html">Anima Finetune</a> — DiT 整模微调（高显存）</li>'
    '<li><a href="/dreambooth/index.html">Stable Diffusion</a> — 默认 SDXL Finetune，可切换 SD1.5 Dreambooth</li>'
    "</ul></li></ul></li>"
    "<li><strong>填写参数并开训</strong>：中栏表单 → 右栏「开始训练」。</li>"
    '<li><strong>查看进度</strong>：<a href="/train-monitor" target="_blank" rel="noopener noreferrer">训练监控</a>、'
    '<a href="/tensorboard.html">Tensorboard</a>。</li>'
    "</ol></div></div>"
)

GUIDE_MIGRATE_INNER = (
    '<div class="sd-guide-migrate">'
    '<h2 id="从秋叶版迁移" tabindex="-1">'
    '<a class="header-anchor" href="#从秋叶版迁移" aria-hidden="true">#</a> 从秋叶版迁移</h2>'
    "<p>若你使用过 <strong>Akegarasu/lora-scripts</strong>（秋叶一键包），本版主要变化：</p>"
    "<ul>"
    "<li><strong>品牌</strong>：项目名 <strong>lora-scripts-next</strong> / Next Trainer，侧栏按「训练 / 工具 / 帮助 / 其他」分组。</li>"
    '<li><strong>导航</strong>：LoRA 与全量微调分栏；原「新手 / 专家」不再平铺（SD1.5 精简页：<a href="/lora/basic.html">/lora/basic.html</a>）。</li>'
    "<li><strong>Anima</strong>：LoRA 与 Finetune 分入口（Qwen + T5 + DiT）。</li>"
    '<li><strong>监控</strong>：独立 <a href="/train-monitor" target="_blank" rel="noopener noreferrer">训练监控页</a>、Loss 曲线、<code>/train-log</code> 日志流。</li>'
    '<li>更多版本说明见 <a href="/other/changelog.html">更新日志</a>。</li>'
    "</ul></div>"
)


def build_full_guide_pager_html(*, compact: bool = False) -> str:
    intro = re.sub(r">\s+<", "><", GUIDE_INTRO_INNER) if compact else GUIDE_INTRO_INNER
    migrate = re.sub(r">\s+<", "><", GUIDE_MIGRATE_INNER) if compact else GUIDE_MIGRATE_INNER
    fast = build_fast_guide_section_html(compact=compact)
    return (
        '<div class="sd-guide sd-guide-pager" data-guide-pager>'
        '<div class="sd-guide-pager__viewport"><div class="sd-guide-pager__pages">'
        '<section class="sd-guide-pager__page is-active" data-guide-page="0" id="guide-page-intro" aria-label="新手上路">'
        f"{intro}</section>"
        '<section class="sd-guide-pager__page" data-guide-page="1" id="guide-page-migrate" aria-label="从秋叶版迁移">'
        f"{migrate}</section>"
        '<section class="sd-guide-pager__page" data-guide-page="2" id="guide-page-fast" aria-label="Anima Fast">'
        f"{fast}</section>"
        "</div></div>"
        '<nav class="sd-guide-pager__nav" aria-label="新手上路翻页">'
        '<button type="button" class="sd-guide-pager__btn" data-guide-prev disabled>上一页</button>'
        '<span class="sd-guide-pager__count" data-guide-count>1 / 3</span>'
        '<button type="button" class="sd-guide-pager__btn" data-guide-next>下一页</button>'
        "</nav></div>"
    )

FAST_PROGRESS_HTML = """
<div data-anima-fast-progress hidden style="margin:10px 0 12px 0;padding:10px;border:1px solid var(--c-border);border-radius:6px;background:var(--c-bg-light);">
  <div data-anima-fast-progress-text style="font-size:13px;margin-bottom:8px;">准备安装</div>
  <div style="height:8px;background:var(--c-border);border-radius:999px;overflow:hidden;">
    <div data-anima-fast-progress-bar style="width:0%;height:100%;background:linear-gradient(90deg,#6366f1,#22c55e);transition:width .25s ease;"></div>
  </div>
  <div data-anima-fast-progress-meta style="font-size:12px;opacity:.72;margin-top:6px;">0% · 预计剩余：正在估算</div>
</div>
""".strip()

FAST_UI_CSS_MARKER = "/* ----- Anima Fast UI ----- */"
FAST_INSTALL_LOG_STYLE = (
    "max-height:140px;overflow:auto;margin:8px 0 10px 0;padding:10px;"
    "border:1px solid var(--c-border);border-radius:6px;font-size:12px;"
    "line-height:1.45;white-space:pre-wrap;"
)

INSTALL_GUARD = r''';(()=>{if(window.__ANIMA_FAST_INSTALL_GUARD__)return;window.__ANIMA_FAST_INSTALL_GUARD__=true;const CONFIRM="Anima Fast 为进阶实验插件，需 NVIDIA GPU、约 16GB+ 显存，并会下载独立 Python 环境（数 GB）。\n\n确认已了解并继续安装？";let last={feature_enabled:true,state:"unknown"},es=null,tmr=null,scheduled=false;function q(s){return Array.from(document.querySelectorAll(s))}function isFastPage(){return/^\/lora\/anima-fast(\.html|\.md)?$/.test(location.pathname)}function markPage(){document.body.classList.toggle("anima-fast-page",isFastPage())}function setControls(d){if(!isFastPage())return;const kill=!d.feature_enabled,working=d.state==="installing"||d.state==="auditing",ready=d.state==="ready";q("[data-anima-fast-install]").forEach(b=>{b.disabled=kill||working;b.setAttribute("aria-disabled",b.disabled?"true":"false")});q(".right-container button").forEach(b=>{const t=(b.textContent||"").trim();if(t==="开始训练"||t==="✨加载训练预设✨"||t==="导入配置文件"||t==="保存参数"){b.disabled=kill||!ready;b.setAttribute("aria-disabled",b.disabled?"true":"false")}});document.body.classList.toggle("anima-fast-disabled",kill||!ready)}function label(d){if(!d.feature_enabled)return"功能已关闭";return d.state==="ready"?"插件已就绪":d.state==="installing"?"安装中":d.state==="auditing"?"审计中":d.state==="broken"?"需修复":d.state==="installed_unverified"?"待审计":"进阶插件 · 待开启"}function appendLog(x){const p=document.querySelector("[data-anima-fast-log]");if(!p)return;p.hidden=false;p.textContent+=(p.textContent?"\n":"")+x;p.scrollTop=p.scrollHeight}function apply(d){last=d||last;setControls(last);const n=document.querySelector("[data-anima-fast-status]");if(n)n.textContent=label(last);const a=last.facts&&last.facts.audit;if(a&&!a.ok&&a.errors)appendLog("[audit] "+a.errors.join("; "))}async function status(){try{const r=await fetch("/api/engines/anima-fast/status"),j=await r.json();apply(Object.assign({feature_enabled:true},j.data||{state:"unknown"}))}catch(e){const n=document.querySelector("[data-anima-fast-status]");if(n)n.textContent="状态检查失败"}}function scheduleStatus(){if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;status()},120)}function openLog(url){if(!url||!window.EventSource)return;if(es)es.close();appendLog("[log] streaming "+url);es=new EventSource(url);es.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.text)appendLog(d.text);if(d.done){appendLog("[log] done");es.close();es=null;if(tmr){clearInterval(tmr);tmr=null}status()}}catch(_){appendLog(e.data)}};es.onerror=()=>{appendLog("[log] stream disconnected");if(es){es.close();es=null}status()}}document.addEventListener("click",async e=>{const t=e.target&&e.target.closest&&e.target.closest("[data-anima-fast-guide-toggle]");if(t&&isFastPage()){const p=t.closest(".anima-fast-guide-collapsible"),b=p&&p.querySelector(".anima-fast-dataset-guide__body");if(b){const o=b.hidden;b.hidden=!o;t.setAttribute("aria-expanded",o?"true":"false");p.classList.toggle("is-open",o);try{localStorage.setItem("anima-fast-guide-open",o?"1":"0")}catch(_){}}return}const b=e.target&&e.target.closest&&e.target.closest("[data-anima-fast-install]");if(!b||!isFastPage())return;if(!last.feature_enabled)return;if(!window.confirm(CONFIRM))return;b.disabled=true;const s=document.querySelector("[data-anima-fast-status]"),p=document.querySelector("[data-anima-fast-log]");if(p){p.hidden=false;p.textContent=""}if(s)s.textContent="安装任务启动中";try{const r=await fetch("/api/engines/anima-fast/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dry_run:false})}),j=await r.json();if(j.status!=="success"){if(s)s.textContent=j.message||"安装失败";appendLog("[error] "+(j.message||"install failed"));return}const d=j.data||{};if(s)s.textContent="安装中";appendLog("[task] "+(d.task_id||"unknown"));openLog(d.log_stream||d.log_stream_url||(d.task_id?"/api/engines/anima-fast/install/log/stream/"+d.task_id:""));if(tmr)clearInterval(tmr);tmr=setInterval(status,2000);status()}catch(t){if(s)s.textContent="安装失败";appendLog("[error] "+t)}finally{setTimeout(()=>setControls(last),250)}});function initGuideToggle(){if(!isFastPage())return;q("[data-anima-fast-guide-toggle]").forEach(t=>{const p=t.closest(".anima-fast-guide-collapsible"),b=p&&p.querySelector(".anima-fast-dataset-guide__body");if(!b)return;let o=false;try{o=localStorage.getItem("anima-fast-guide-open")==="1"}catch(_){}b.hidden=!o;t.setAttribute("aria-expanded",o?"true":"false");p.classList.toggle("is-open",o)})}new MutationObserver(scheduleStatus).observe(document.documentElement,{childList:true,subtree:true});document.addEventListener("DOMContentLoaded",()=>{markPage();initGuideToggle();status()});markPage();initGuideToggle();setTimeout(status,0)})();'''


def _guide_html_for_vue() -> str:
    """Escape for embedding in Vue render chunk as innerHTML container."""
    return json.dumps(FAST_DATASET_GUIDE_HTML)


def write_page_chunks() -> None:
    credit_json = json.dumps(FAST_CREDIT_HTML)
    link_json = json.dumps(FAST_GUIDE_LINK_HTML)
    progress_json = json.dumps(FAST_PROGRESS_HTML)
    page = (
        f'import{{_ as s,o as t,c as o,a as e,b as a}}from"{APP_JS_MODULE}";'
        "const _={},"
        f'x=e("div",{{class:"anima-fast-credit-root",innerHTML:{credit_json}}}),'
        f'l=e("div",{{class:"anima-fast-guide-link-root",innerHTML:{link_json}}}),'
        'm=e("div",{class:"anima-fast-install-panel",style:"display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0;"},['
        'e("button",{"data-anima-fast-install":"",type:"button",class:"el-button el-button--primary is-plain"},['
        'e("span",null,"安装 Fast 训练环境")]),'
        'e("span",{"data-anima-fast-status":"",style:"font-size:13px;opacity:.8;"},"检查中")],-1),'
        f'v=e("div",{{class:"anima-fast-progress-root",innerHTML:{progress_json}}}),'
        f'f=e("pre",{{"data-anima-fast-log":"",hidden:"",style:{json.dumps(FAST_INSTALL_LOG_STYLE)}}},null,-1),'
        "parts=[x,l,m,v,f];"
        'function i(h,u){return t(),o("div",{class:"anima-fast-intro-wrap"},parts)}'
        'var p=s(_,[["render",i],["__file","anima-fast.html.vue"]]);export{p as default};'
    )
    PAGE_JS.write_text(page, encoding="utf-8")

    data = {
        "key": ROUTE_KEY,
        "path": "/lora/anima-fast.html",
        "title": PAGE_TITLE,
        "lang": "en-US",
        "frontmatter": {"example": True, "trainType": TRAIN_TYPE},
        "excerpt": "",
        "headers": [],
        "filePathRelative": "lora/anima-fast.md",
    }
    DATA_JS.write_text(f"const e=JSON.parse({json.dumps(json.dumps(data, ensure_ascii=False), ensure_ascii=False)});export{{e as data}};\n", encoding="utf-8")


def patch_html() -> None:
    html = SOURCE_HTML.read_text(encoding="utf-8")
    html = GUARD_PATTERN.sub("", html)
    html = html.replace("Anima Stable Diffusion LoRA | SD 训练 UI", "Anima LoRA Fast | SD 训练 UI")
    html = html.replace("/assets/sd3.html.1a4bf31e.js", f"/assets/{PAGE_JS.name}")
    html = html.replace("/assets/sd3.html.eaeb05e1.js", f"/assets/{DATA_JS.name}")
    main_block = (
        '<main><div class="anima-fast-intro-wrap">'
        f'{FAST_CREDIT_HTML}'
        f'{FAST_GUIDE_LINK_HTML}'
        '<div class="anima-fast-install-panel" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0;">'
        '<button data-anima-fast-install type="button" class="el-button el-button--primary is-plain">'
        '<span>安装 Fast 训练环境</span></button>'
        '<span data-anima-fast-status style="font-size:13px;opacity:.8;">检查中</span></div>'
        f'{FAST_PROGRESS_HTML}'
        f'<pre data-anima-fast-log hidden style="{FAST_INSTALL_LOG_STYLE}"></pre>'
        '</div></main>'
    )
    html = html.replace(
        '<main><div><h1 id="sd3-训练-专家模式" tabindex="-1"><a class="header-anchor" href="#sd3-训练-专家模式" aria-hidden="true">#</a> Anima Stable Diffusion LoRA</h1><p>Anima DiT 模型 LoRA 训练 专家模式</p><p>Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数</p></div></main>',
        main_block,
    )
    html = html.replace("sd3-训练-专家模式", "anima-fast-lora")
    html = _ensure_install_script(html)
    TARGET_HTML.parent.mkdir(parents=True, exist_ok=True)
    TARGET_HTML.write_text(html, encoding="utf-8")


def _replace_once(content: str, old: str, new: str) -> str:
    if new in content:
        return content
    if old not in content:
        raise RuntimeError(f"pattern not found: {old[:120]}")
    return content.replace(old, new, 1)


def patch_app_js() -> None:
    js = GUARD_PATTERN.sub("", APP_JS.read_text(encoding="utf-8"))
    if ROUTE_KEY in js and PAGE_JS.name in js and DATA_JS.name in js:
        APP_JS.write_text(js, encoding="utf-8")
        return
    js = _replace_once(
        js,
        '"v-0dc76a3b":()=>wt(()=>import("./sd3.html.eaeb05e1.js"),[]).then(({data:e})=>e)',
        '"v-0dc76a3b":()=>wt(()=>import("./sd3.html.eaeb05e1.js"),[]).then(({data:e})=>e),"v-anima-fast":()=>wt(()=>import("./anima-fast.html.data.js"),[]).then(({data:e})=>e)',
    )
    js = _replace_once(
        js,
        '"v-0dc76a3b":Jt(()=>wt(()=>import("./sd3.html.1a4bf31e.js"),[]))',
        '"v-0dc76a3b":Jt(()=>wt(()=>import("./sd3.html.1a4bf31e.js"),[])),"v-anima-fast":Jt(()=>wt(()=>import("./anima-fast.html.page.js"),[]))',
    )
    js = _replace_once(
        js,
        '["v-0dc76a3b","/lora/sd3.html",{title:"SD3 \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},["/lora/sd3","/lora/sd3.md"]]',
        '["v-0dc76a3b","/lora/sd3.html",{title:"SD3 \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},["/lora/sd3","/lora/sd3.md"]],["v-anima-fast","/lora/anima-fast.html",{title:"Anima LoRA \\u00b7 Fast \\u6a21\\u5f0f"},["/lora/anima-fast","/lora/anima-fast.md"]]',
    )
    APP_JS.write_text(js, encoding="utf-8")


def _ensure_install_script(html: str) -> str:
    script = f'<script src="/assets/{INSTALL_JS.name}" defer></script>'
    if script in html:
        return html
    marker = '<script type="module" src="/assets/app.547295de.js" defer></script>'
    if marker in html:
        return html.replace(marker, script + marker, 1)
    return html.replace("</body>", f"    {script}\n  </body>")


def patch_prefetch_links() -> None:
    page_link = f'<link rel="prefetch" href="/assets/{PAGE_JS.name}">'
    data_link = f'<link rel="prefetch" href="/assets/{DATA_JS.name}">'
    for path in sorted(DIST.rglob("*.html")):
        html = path.read_text(encoding="utf-8")
        marker = '<link rel="prefetch" href="/assets/sd3.html.1a4bf31e.js">'
        changed = False
        if marker in html and (page_link not in html or data_link not in html):
            html = html.replace(marker, marker + data_link + page_link, 1)
            changed = True
        updated = _ensure_install_script(html)
        if updated != html:
            html = updated
            changed = True
        if changed:
            path.write_text(html, encoding="utf-8")


def _fast_ui_css_block() -> str:
    return f"""
{FAST_UI_CSS_MARKER}
.example-container > .right-container .anima-fast-credit {{
  margin: 0.35rem 0 0.5rem;
  padding: 0.45rem 0.65rem;
  border-radius: var(--sd-radius-md, 8px);
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--c-text-lighter, #606266);
  background: color-mix(in srgb, var(--el-color-success, #67c23a) 7%, var(--c-bg, #fff));
  border: 1px solid color-mix(in srgb, var(--el-color-success, #67c23a) 24%, var(--c-border, #dcdfe6));
}}

.example-container > .right-container .anima-fast-guide-link {{
  margin: 0 0 0.65rem;
  font-size: 13px;
  line-height: 1.55;
  color: var(--c-text-lighter, #606266);
}}

.example-container > .right-container .anima-fast-guide-link a {{
  color: var(--el-color-primary, #409eff);
  font-weight: 600;
  text-decoration: none;
}}

.example-container > .right-container .anima-fast-guide-link a:hover {{
  text-decoration: underline;
}}

.example-container > .right-container .anima-fast-doc-links {{
  margin: 0 0 0.75rem;
  font-size: 13px;
  line-height: 1.55;
  color: var(--c-text-lighter, #606266);
}}

.example-container > .right-container .anima-fast-doc-links a {{
  color: var(--el-color-primary, #409eff);
  font-weight: 600;
  text-decoration: none;
}}

.example-container > .right-container .anima-fast-doc-links a:hover {{
  text-decoration: underline;
}}

.example-container > .right-container .anima-fast-credit a {{
  color: var(--el-color-primary, #409eff);
  font-weight: 600;
  text-decoration: none;
}}

.example-container > .right-container .anima-fast-credit a:hover {{
  text-decoration: underline;
}}

body.anima-fast-page .theme-container.no-navbar .example-container {{
  height: 100vh;
  min-height: 0;
  align-items: stretch;
}}

body.anima-fast-page .example-container > .schema-container,
body.anima-fast-page .example-container > .right-container {{
  min-height: 0;
  overflow: hidden;
}}

body.anima-fast-page .example-container > .right-container > section:first-of-type {{
  flex: 0 0 auto;
  overflow: visible;
  padding-top: 0.25rem;
}}

body.anima-fast-page .example-container > .right-container > section:first-of-type .el-scrollbar,
body.anima-fast-page .example-container > .right-container > section:first-of-type .el-scrollbar__wrap,
body.anima-fast-page .example-container > .right-container > section:first-of-type .el-scrollbar__view {{
  height: auto !important;
  max-height: none !important;
}}

body.anima-fast-page .example-container > .right-container > section:first-of-type main {{
  padding-top: 0;
}}

body.anima-fast-page [data-anima-fast-log] {{
  max-height: 140px !important;
  margin: 8px 0 10px 0 !important;
}}

body.anima-fast-page .example-container > .right-container > section:has(.params-section) {{
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

body.anima-fast-page .example-container > .right-container > section:has(.params-section) .params-section {{
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

body.anima-fast-page .example-container > .right-container > section:has(.params-section) .params-section .el-scrollbar {{
  flex: 1 1 auto;
  min-height: 0;
}}

body.anima-fast-page .example-container > .right-container > section:has(.params-section) .params-section .el-scrollbar__wrap {{
  max-height: none !important;
  overflow: auto !important;
}}

body.anima-fast-page .example-container > .right-container > .el-row {{
  flex: 0 0 auto;
}}

.example-container > .right-container .anima-fast-intro-wrap {{
  padding-bottom: 0.25rem;
}}

.anima-fast-dataset-guide__body {{
  margin-top: 0.45rem;
  padding: 0.75rem 0.9rem;
  border-radius: var(--sd-radius-md, 8px);
  font-size: 13px;
  line-height: 1.65;
  color: var(--c-text, #303133);
  background: var(--c-bg-light, #f8f9fb);
  border: 1px solid var(--c-border, #e4e7ed);
  border-left: 3px solid var(--el-color-primary, #409eff);
}}

.anima-fast-dataset-guide__body p {{
  margin: 0.35rem 0;
}}

.anima-fast-dataset-guide__body ul {{
  margin: 0.35rem 0 0.5rem 1.1rem;
  padding: 0;
}}

.anima-fast-dataset-guide__body li {{
  margin: 0.2rem 0;
}}

.anima-fast-dataset-guide__body code {{
  font-size: 12px;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--c-bg-mute, #fff);
  border: 1px solid var(--c-border, #e4e7ed);
}}

.anima-fast-dataset-guide__highlight {{
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 10%, var(--c-bg, #fff));
  border: 1px solid color-mix(in srgb, var(--el-color-warning, #e6a23c) 28%, transparent);
}}

.anima-fast-dataset-guide__note {{
  font-size: 12.5px;
  color: var(--c-text-lighter, #606266);
}}

body.anima-fast-page .example-container .schema-container .el-collapse {{
  border: none;
}}

body.anima-fast-page .example-container .schema-container .el-collapse-item__header {{
  background: transparent !important;
  border: none !important;
  border-bottom: 1px solid var(--c-border, #e4e7ed) !important;
  border-radius: 0 !important;
  height: auto !important;
  line-height: 1.4 !important;
  padding: 0 0 0.5rem !important;
  margin: 1.25rem 0 0.5rem !important;
  font-size: 15px !important;
  font-weight: 600 !important;
  color: var(--c-text, #303133) !important;
}}

body.anima-fast-page .example-container .schema-container .el-collapse-item__wrap {{
  border-bottom: none;
}}

body.anima-fast-page .example-container .schema-container .el-collapse-item__content {{
  padding-bottom: 0.25rem;
}}

html.dark .example-container > .right-container .anima-fast-credit {{
  background: color-mix(in srgb, var(--el-color-success, #67c23a) 12%, var(--c-bg, #22272e));
  border-color: color-mix(in srgb, var(--el-color-success, #67c23a) 28%, var(--c-border, #3d444d));
  color: var(--c-text-lighter, #adbac7);
}}

html.dark .example-container > .right-container .anima-fast-dataset-guide__body,
html.dark main.page .theme-default-content .anima-fast-dataset-guide__body {{
  background: color-mix(in srgb, var(--c-bg-light, #2d333b) 90%, var(--c-bg, #22272e));
  border-color: var(--c-border, #3d444d);
}}

html.dark .example-container > .right-container .anima-fast-dataset-guide__body code,
html.dark main.page .theme-default-content .anima-fast-dataset-guide__body code {{
  background: color-mix(in srgb, var(--c-bg, #22272e) 80%, transparent);
  border-color: var(--c-border, #3d444d);
}}

html.dark .example-container > .right-container .anima-fast-dataset-guide__highlight,
html.dark main.page .theme-default-content .anima-fast-dataset-guide__highlight {{
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 14%, var(--c-bg, #22272e));
}}

html.dark body.anima-fast-page .example-container .schema-container .el-collapse-item__header {{
  color: var(--c-text, #adbac7) !important;
  border-bottom-color: var(--c-border, #3d444d) !important;
}}

.anima-fast-compile-warn {{
  margin: 0.35rem 0 0.75rem;
  padding: 0.55rem 0.75rem;
  border-radius: var(--sd-radius-md, 8px);
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--el-color-warning-dark-2, #b88230);
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 12%, var(--c-bg, #fff));
  border: 1px solid color-mix(in srgb, var(--el-color-warning, #e6a23c) 35%, var(--c-border, #dcdfe6));
}}

.anima-fast-compile-warn[hidden] {{
  display: none !important;
}}

body.anima-fast-page .el-form-item.anima-fast-compile-locked .el-switch {{
  opacity: 0.55;
  pointer-events: none;
}}

body.anima-fast-page .k-schema-item.anima-fast-compile-locked .el-switch {{
  opacity: 0.55;
  pointer-events: none;
}}

body.anima-fast-page .el-form-item.anima-fast-compile-locked .el-select {{
  opacity: 0.55;
  pointer-events: none;
}}

body.anima-fast-page .k-schema-item.anima-fast-compile-locked .el-select {{
  opacity: 0.55;
  pointer-events: none;
}}

body.anima-fast-page .el-form-item.anima-fast-audit-limited .el-form-item__label::after {{
  content: "（部分选项需修复插件环境）";
  margin-left: 4px;
  color: var(--el-color-warning-dark-2, #b88230);
  font-size: 12px;
  font-weight: 400;
}}

body.anima-fast-page .k-schema-item.anima-fast-audit-limited .k-schema-main::after {{
  content: "（部分选项需修复插件环境）";
  margin-left: 4px;
  color: var(--el-color-warning-dark-2, #b88230);
  font-size: 12px;
  font-weight: 400;
}}

body.anima-fast-page .el-select-dropdown__item.anima-fast-option-disabled {{
  opacity: 0.45;
  cursor: not-allowed;
  color: var(--el-text-color-disabled, #a8abb2) !important;
}}

body.anima-fast-page .el-select-dropdown__item.anima-fast-option-disabled::after {{
  content: " 不可用";
  margin-left: 4px;
  font-size: 12px;
  color: var(--el-color-warning-dark-2, #b88230);
}}

html.dark .anima-fast-compile-warn {{
  color: #e6c27a;
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 16%, var(--c-bg, #22272e));
  border-color: color-mix(in srgb, var(--el-color-warning, #e6a23c) 32%, var(--c-border, #3d444d));
}}
/* ----- /Anima Fast UI ----- */
"""


def _upsert_css_block(css: str, block: str) -> str:
    end_marker = "/* ----- /Anima Fast UI ----- */"
    if FAST_UI_CSS_MARKER in css and end_marker in css:
        start = css.index(FAST_UI_CSS_MARKER)
        end = css.index(end_marker) + len(end_marker)
        return css[:start] + block.strip() + css[end:]
    legacy = re.compile(
        r"/\* ----- Anima Fast：.*?(?=/\* ----- [^/]|\Z)",
        re.DOTALL,
    )
    css = legacy.sub("", css)
    return css.rstrip() + "\n" + block.strip() + "\n"


def _sync_style_bundle(polish_css: str) -> None:
    if not STYLE_CSS.exists():
        return
    style = STYLE_CSS.read_text(encoding="utf-8")
    anchor = style.find("/* ========== SD-Trainer UI polish")
    if anchor < 0:
        return
    STYLE_CSS.write_text(style[:anchor] + polish_css, encoding="utf-8")


def _guide_pager_css_block() -> str:
    return f"""{GUIDE_PAGER_CSS_MARKER}
main.page .theme-default-content .sd-guide-anima-fast {{
  margin-top: 1.5rem;
  padding: 1.2rem 1.35rem 1.1rem;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 12%, var(--c-border));
  background: color-mix(in srgb, var(--el-color-primary) 3%, #fff);
}}

main.page .theme-default-content .sd-guide-anima-fast h2 {{
  margin: 0 0 0.75rem;
  padding-bottom: 0.4rem;
  font-size: 1.2rem;
  border-bottom: 1px solid var(--c-border);
}}

main.page .theme-default-content .sd-guide-anima-fast .anima-fast-dataset-guide__body {{
  margin-top: 0.85rem;
}}

main.page .theme-default-content .sd-guide-pager {{
  display: flex;
  flex-direction: column;
  max-width: 56rem;
  margin: 0 auto;
  min-height: min(62vh, 560px);
  max-height: min(84vh, 860px);
  padding: 1.25rem 1.5rem 1rem;
  overflow: hidden;
}}

main.page .theme-default-content .sd-guide-pager__viewport {{
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-bottom: 0.35rem;
}}

main.page .theme-default-content .sd-guide-pager__page {{
  display: none;
  padding-bottom: 0.5rem;
}}

main.page .theme-default-content .sd-guide-pager__page.is-active {{
  display: block;
}}

main.page .theme-default-content .sd-guide-pager__page .sd-guide-migrate,
main.page .theme-default-content .sd-guide-pager__page .sd-guide-anima-fast {{
  margin-top: 0;
}}

main.page .theme-default-content .sd-guide-pager__page .sd-guide-intro {{
  align-items: start;
}}

main.page .theme-default-content .sd-guide-pager__page .sd-guide-intro--text-only {{
  display: block;
}}

main.page .theme-default-content .sd-guide-pager__page .sd-guide-intro--text-only .sd-guide-intro__body {{
  max-width: none;
}}

@media (max-height: 820px) {{
  main.page .theme-default-content .sd-guide-pager {{
    min-height: min(56vh, 480px);
    max-height: calc(100vh - 4.5rem);
  }}
}}

main.page .theme-default-content .sd-guide-pager__nav {{
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 0.85rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--c-border, #e4e7ed);
}}

main.page .theme-default-content .sd-guide-pager__btn {{
  min-width: 5.5rem;
  padding: 0.45rem 0.9rem;
  border-radius: var(--sd-radius-md, 8px);
  border: 1px solid var(--c-border, #dcdfe6);
  background: var(--c-bg-mute, #fff);
  color: var(--c-text, #303133);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}}

main.page .theme-default-content .sd-guide-pager__btn:hover:not(:disabled) {{
  border-color: color-mix(in srgb, var(--el-color-primary) 35%, var(--c-border));
  background: color-mix(in srgb, var(--el-color-primary) 6%, var(--c-bg-mute, #fff));
}}

main.page .theme-default-content .sd-guide-pager__btn:disabled {{
  opacity: 0.45;
  cursor: not-allowed;
}}

main.page .theme-default-content .sd-guide-pager__count {{
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-lighter, #606266);
  letter-spacing: 0.02em;
}}

html.dark main.page .theme-default-content .anima-fast-dataset-guide__body {{
  background: color-mix(in srgb, var(--c-bg-light, #2d333b) 90%, var(--c-bg, #22272e));
  border-color: var(--c-border, #3d444d);
}}

html.dark main.page .theme-default-content .anima-fast-dataset-guide__body code {{
  background: color-mix(in srgb, var(--c-bg, #22272e) 80%, transparent);
  border-color: var(--c-border, #3d444d);
}}

html.dark main.page .theme-default-content .anima-fast-dataset-guide__highlight {{
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 14%, var(--c-bg, #22272e));
}}
/* ----- /Guide pager ----- */
"""


def _upsert_guide_pager_css(css: str, block: str) -> str:
    end_marker = "/* ----- /Guide pager ----- */"
    if GUIDE_PAGER_CSS_MARKER in css and end_marker in css:
        start = css.index(GUIDE_PAGER_CSS_MARKER)
        end = css.index(end_marker) + len(end_marker)
        return css[:start] + block.strip() + css[end:]
    return css.rstrip() + "\n" + block.strip() + "\n"


def _escape_js_template(html: str) -> str:
    return html.replace("\\", "\\\\").replace("`", "\\`").replace("\r", "").replace("\n", "")


def _fix_guide_html_assets(html: str) -> str:
    """Ensure guide SSR head preloads point at existing chunk files."""
    replacements = (
        ("changelog.html.a1b2c3d4.js", "guide.html.b8e2d701.js"),
        ("changelog.html.e5f6a7b8.js", "guide.html.c3f4a902.js"),
        ("guide.html.a1b2c3d4.js", "guide.html.b8e2d701.js"),
        ("guide.html.e5f6a7b8.js", "guide.html.c3f4a902.js"),
        ("guide.html.c3f4a902.js.js", "guide.html.c3f4a902.js"),
        ("guide.html.b8e2d701.js.js", "guide.html.b8e2d701.js"),
    )
    for old, new in replacements:
        html = html.replace(old, new)
    return html


def rebuild_guide_html() -> None:
    guide_html_path = DIST / "help" / "guide.html"
    html = guide_html_path.read_text(encoding="utf-8")
    start = html.index('<div class="sd-guide')
    end = html.index("</div></div><!--[--><!--]--></div><footer", start)
    new_body = build_full_guide_pager_html(compact=True)
    html = html[:start] + new_body + html[end + len("</div>") :]
    guide_html_path.write_text(_fix_guide_html_assets(html), encoding="utf-8")


def _assert_guide_page_js_valid(source: str, path: Path) -> None:
    path.write_text(source, encoding="utf-8")
    if "sd-guide-pager" not in source or "data-guide-pager" not in source:
        raise RuntimeError(f"guide page chunk missing pager markers: {path}")
    if "sd-guide-anima-fast" not in source or "sd-guide-intro" not in source:
        raise RuntimeError(f"guide page chunk missing expected markers: {path}")
    if source.count("`") % 2 != 0:
        raise RuntimeError(f"guide page chunk has unbalanced backticks: {path}")
    try:
        subprocess.run(
            ["node", "--check", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        if "`\n" in source or "\n  <" in source:
            raise RuntimeError(f"guide page chunk looks multiline-broken: {path}") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"guide page chunk syntax invalid: {path}\n{detail}") from exc


def rebuild_guide_page_js() -> None:
    guide_js = ASSETS / "guide.html.c3f4a902.js"
    inner = _escape_js_template(build_full_guide_pager_html(compact=True))
    source = (
        'import{_ as n,o as s,c as a,a as e,e as i}from"'
        + APP_JS_MODULE
        + '";'
        "const _={},h=i(`"
        + inner
        + "`);"
        'function u(){return s(),a("div",null,[e("span",{"aria-hidden":"true",style:"display:none"},".",-1),h])}'
        'var x=n(_,[["render",u],["__file","guide.html.vue"]]);export{x as default};'
    )
    _assert_guide_page_js_valid(source, guide_js)


def patch_guide_pager() -> None:
    rebuild_guide_html()
    rebuild_guide_page_js()


def append_guide_pager_css() -> None:
    if not POLISH_CSS.exists():
        return
    block = _guide_pager_css_block()
    css = _upsert_guide_pager_css(POLISH_CSS.read_text(encoding="utf-8"), block)
    POLISH_CSS.write_text(css, encoding="utf-8")
    _sync_style_bundle(css)


def _guide_page_js_valid() -> bool:
    guide_js = ASSETS / "guide.html.c3f4a902.js"
    if not guide_js.is_file():
        return False
    text = guide_js.read_text(encoding="utf-8")
    if "sd-guide-pager" not in text or "data-guide-pager" not in text:
        return False
    if "sd-guide-anima-fast" not in text or "sd-guide-intro" not in text:
        return False
    if text.count("`") % 2 != 0 or "\n  <" in text:
        return False
    try:
        subprocess.run(["node", "--check", str(guide_js)], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return text.count("\n") <= 1
    return True


def append_guide_css() -> None:
    if not POLISH_CSS.exists():
        return
    block = _fast_ui_css_block()
    css = _upsert_css_block(POLISH_CSS.read_text(encoding="utf-8"), block)
    POLISH_CSS.write_text(css, encoding="utf-8")
    _sync_style_bundle(css)


def assert_registered() -> None:
    app = APP_JS.read_text(encoding="utf-8")
    html = TARGET_HTML.read_text(encoding="utf-8")
    checks = [
        (TARGET_HTML.exists(), "target html exists"),
        (PAGE_JS.exists(), "page chunk exists"),
        (DATA_JS.exists(), "data chunk exists"),
        ("/lora/anima-fast.html" in app, "route registered"),
        (TRAIN_TYPE in DATA_JS.read_text(encoding="utf-8"), "train type in data"),
        (PAGE_JS.name in html and DATA_JS.name in html, "html preloads chunks"),
        (GUIDE_CSS_MARKER in POLISH_CSS.read_text(encoding="utf-8"), "dataset guide css marker"),
        (CREDIT_CSS_MARKER in html, "open-source credit in html"),
        ("anima-fast-guide-link" in html, "guide portal link in html"),
        ("/help/guide.html#anima-fast-lora" in html, "guide anchor link in html"),
        ("data-anima-fast-install" in html, "install panel in html"),
        (FAST_UI_CSS_MARKER in POLISH_CSS.read_text(encoding="utf-8"), "fast ui css block"),
        (INSTALL_JS.name in html, "install guard script in target html"),
        (INSTALL_JS.name in (DIST / "index.html").read_text(encoding="utf-8"), "install guard script in root html"),
        ("sd-guide-pager" in (DIST / "help" / "guide.html").read_text(encoding="utf-8"), "guide pager in html"),
        (_guide_page_js_valid(), "guide page chunk syntax"),
    ]
    missing = [label for ok, label in checks if not ok]
    if missing:
        raise RuntimeError("Anima Fast frontend patch incomplete: " + ", ".join(missing))


def main() -> None:
    write_page_chunks()
    patch_html()
    patch_app_js()
    patch_prefetch_links()
    append_guide_css()
    append_guide_pager_css()
    patch_guide_pager()
    assert_registered()
    print("patched Anima Fast frontend entry")


if __name__ == "__main__":
    main()
