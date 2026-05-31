#!/usr/bin/env python3
"""Register the Anima Fast trainer entry in the built VuePress frontend."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"
ASSETS = DIST / "assets"
APP_JS = ASSETS / "app.547295de.js"

SOURCE_HTML = DIST / "lora/sd3.html"
TARGET_HTML = DIST / "lora/anima-fast.html"
PAGE_JS = ASSETS / "anima-fast.html.page.js"
DATA_JS = ASSETS / "anima-fast.html.data.js"

POLISH_CSS = ASSETS / "sd-trainer-ui-polish.css"
STYLE_CSS = ASSETS / "style.874872ce.css"

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
    "Fast 训练引擎来自开源项目 "
    '<a href="https://github.com/sorryhyun/anima_lora" target="_blank" rel="noopener noreferrer">'
    "sorryhyun/anima_lora</a>。"
    "感谢原作者与社区的开发与分享；本页以可选插件形式集成，遵循各自开源许可。"
    "</p>"
)

FAST_DOC_URL = "https://github.com/wochenlong/lora-scripts-next/blob/main/docs/anima-fast.md"

FAST_DOC_LINKS_HTML = (
    '<p class="anima-fast-doc-links">'
    f'<a href="{FAST_DOC_URL}" target="_blank" rel="noopener noreferrer">'
    "Fast 模式训练教程</a>（安装、数据路径、故障排除）"
    ' · <a href="/lora/sd3.html">标准 Kohya 模式</a>'
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

FAST_UI_CSS_MARKER = "/* ----- Anima Fast UI ----- */"

INSTALL_GUARD = r''';(()=>{if(window.__ANIMA_FAST_INSTALL_GUARD__)return;window.__ANIMA_FAST_INSTALL_GUARD__=true;const CONFIRM="Anima Fast 为进阶实验插件，需 NVIDIA GPU、约 16GB+ 显存，并会下载独立 Python 环境（数 GB）。\n\n确认已了解并继续安装？";let last={feature_enabled:true,state:"unknown"},es=null,tmr=null,scheduled=false;function q(s){return Array.from(document.querySelectorAll(s))}function isFastPage(){return/^\/lora\/anima-fast(\.html|\.md)?$/.test(location.pathname)}function markPage(){document.body.classList.toggle("anima-fast-page",isFastPage())}function setControls(d){if(!isFastPage())return;const kill=!d.feature_enabled,working=d.state==="installing"||d.state==="auditing",ready=d.state==="ready";q("[data-anima-fast-install]").forEach(b=>{b.disabled=kill||working;b.setAttribute("aria-disabled",b.disabled?"true":"false")});q(".right-container button").forEach(b=>{const t=(b.textContent||"").trim();if(t==="开始训练"||t==="✨加载训练预设✨"||t==="导入配置文件"||t==="保存参数"){b.disabled=kill||!ready;b.setAttribute("aria-disabled",b.disabled?"true":"false")}});document.body.classList.toggle("anima-fast-disabled",kill||!ready)}function label(d){if(!d.feature_enabled)return"功能已关闭";return d.state==="ready"?"插件已就绪":d.state==="installing"?"安装中":d.state==="auditing"?"审计中":d.state==="broken"?"需修复":d.state==="installed_unverified"?"待审计":"进阶插件 · 待开启"}function appendLog(x){const p=document.querySelector("[data-anima-fast-log]");if(!p)return;p.hidden=false;p.textContent+=(p.textContent?"\n":"")+x;p.scrollTop=p.scrollHeight}function apply(d){last=d||last;setControls(last);const n=document.querySelector("[data-anima-fast-status]");if(n)n.textContent=label(last);const a=last.facts&&last.facts.audit;if(a&&!a.ok&&a.errors)appendLog("[audit] "+a.errors.join("; "))}async function status(){try{const r=await fetch("/api/plugins/anima-lora/status"),j=await r.json();apply(Object.assign({feature_enabled:true},j.data||{state:"unknown"}))}catch(e){const n=document.querySelector("[data-anima-fast-status]");if(n)n.textContent="状态检查失败"}}function scheduleStatus(){if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;status()},120)}function openLog(url){if(!url||!window.EventSource)return;if(es)es.close();appendLog("[log] streaming "+url);es=new EventSource(url);es.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.text)appendLog(d.text);if(d.done){appendLog("[log] done");es.close();es=null;if(tmr){clearInterval(tmr);tmr=null}status()}}catch(_){appendLog(e.data)}};es.onerror=()=>{appendLog("[log] stream disconnected");if(es){es.close();es=null}status()}}document.addEventListener("click",async e=>{const t=e.target&&e.target.closest&&e.target.closest("[data-anima-fast-guide-toggle]");if(t&&isFastPage()){const p=t.closest(".anima-fast-guide-collapsible"),b=p&&p.querySelector(".anima-fast-dataset-guide__body");if(b){const o=b.hidden;b.hidden=!o;t.setAttribute("aria-expanded",o?"true":"false");p.classList.toggle("is-open",o);try{localStorage.setItem("anima-fast-guide-open",o?"1":"0")}catch(_){}}return}const b=e.target&&e.target.closest&&e.target.closest("[data-anima-fast-install]");if(!b||!isFastPage())return;if(!last.feature_enabled)return;if(!window.confirm(CONFIRM))return;b.disabled=true;const s=document.querySelector("[data-anima-fast-status]"),p=document.querySelector("[data-anima-fast-log]");if(p){p.hidden=false;p.textContent=""}if(s)s.textContent="安装任务启动中";try{const r=await fetch("/api/plugins/anima-lora/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dry_run:false})}),j=await r.json();if(j.status!=="success"){if(s)s.textContent=j.message||"安装失败";appendLog("[error] "+(j.message||"install failed"));return}const d=j.data||{};if(s)s.textContent="安装中";appendLog("[task] "+(d.task_id||"unknown"));openLog(d.log_stream||d.log_stream_url||(d.task_id?"/api/plugins/anima-lora/install/log/stream/"+d.task_id:""));if(tmr)clearInterval(tmr);tmr=setInterval(status,2000);status()}catch(t){if(s)s.textContent="安装失败";appendLog("[error] "+t)}finally{setTimeout(()=>setControls(last),250)}});function initGuideToggle(){if(!isFastPage())return;q("[data-anima-fast-guide-toggle]").forEach(t=>{const p=t.closest(".anima-fast-guide-collapsible"),b=p&&p.querySelector(".anima-fast-dataset-guide__body");if(!b)return;let o=false;try{o=localStorage.getItem("anima-fast-guide-open")==="1"}catch(_){}b.hidden=!o;t.setAttribute("aria-expanded",o?"true":"false");p.classList.toggle("is-open",o)})}new MutationObserver(scheduleStatus).observe(document.documentElement,{childList:true,subtree:true});document.addEventListener("DOMContentLoaded",()=>{markPage();initGuideToggle();status()});markPage();initGuideToggle();setTimeout(status,0)})();'''


def _guide_html_for_vue() -> str:
    """Escape for embedding in Vue render chunk as innerHTML container."""
    return json.dumps(FAST_DATASET_GUIDE_HTML)


def write_page_chunks() -> None:
    guide_json = _guide_html_for_vue()
    credit_json = json.dumps(FAST_CREDIT_HTML)
    page = (
        'import{_ as s,o as t,c as o,a as e,b as a}from"./app.547295de.js";'
        "const _={},"
        'c=e("h1",{id:"anima-fast-lora",tabindex:"-1"},['
        'e("a",{class:"header-anchor",href:"#anima-fast-lora","aria-hidden":"true"},"#"),'
        'a(" Anima LoRA · Fast 模式")],-1),'
        f'n=e("p",null,{json.dumps(FAST_PAGE_INTRO)},-1),'
        f'x=e("div",{{class:"anima-fast-credit-root",innerHTML:{credit_json}}}),'
        f'd=e("div",{{class:"anima-fast-doc-links-root",innerHTML:{json.dumps(FAST_DOC_LINKS_HTML)}}}),'
        'r=e("p",null,"标准模式（Kohya）见 /lora/sd3.html",-1),'
        f'g=e("div",{{class:"anima-fast-guide-root",innerHTML:{guide_json}}}),'
        'm=e("div",{class:"anima-fast-install-panel",style:"display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0;"},['
        'e("button",{"data-anima-fast-install":"",type:"button",class:"el-button el-button--primary is-plain"},['
        'e("span",null,"开启插件")]),'
        'e("span",{"data-anima-fast-status":"",style:"font-size:13px;opacity:.8;"},"检查中")],-1),'
        'f=e("pre",{"data-anima-fast-log":"",hidden:"",style:"max-height:260px;overflow:auto;margin:12px 0;padding:10px;border:1px solid var(--c-border);border-radius:6px;font-size:12px;line-height:1.45;white-space:pre-wrap;"},null,-1),'
        "l=[c,n,x,d,r,g,m,f];"
        'function i(h,u){return t(),o("div",{class:"anima-fast-intro-wrap"},l)}'
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
        '<h1 id="anima-fast-lora" tabindex="-1">'
        '<a class="header-anchor" href="#anima-fast-lora" aria-hidden="true">#</a> '
        'Anima LoRA · Fast 模式</h1>'
        f'<p>{FAST_PAGE_INTRO}</p>'
        f'{FAST_CREDIT_HTML}'
        f'{FAST_DOC_LINKS_HTML}'
        f'{FAST_DATASET_GUIDE_HTML}'
        '<div class="anima-fast-install-panel" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0;">'
        '<button data-anima-fast-install type="button" class="el-button el-button--primary is-plain">'
        '<span>开启插件</span></button>'
        '<span data-anima-fast-status style="font-size:13px;opacity:.8;">检查中</span></div>'
        '<pre data-anima-fast-log hidden style="max-height:260px;overflow:auto;margin:12px 0;padding:10px;'
        'border:1px solid var(--c-border);border-radius:6px;font-size:12px;line-height:1.45;white-space:pre-wrap;"></pre>'
        '</div></main>'
    )
    html = html.replace(
        '<main><div><h1 id="sd3-训练-专家模式" tabindex="-1"><a class="header-anchor" href="#sd3-训练-专家模式" aria-hidden="true">#</a> Anima Stable Diffusion LoRA</h1><p>Anima DiT 模型 LoRA 训练 专家模式</p><p>Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数</p></div></main>',
        main_block,
    )
    html = html.replace("sd3-训练-专家模式", "anima-fast-lora")
    html = html.replace("</body>", f"    <script>{INSTALL_GUARD}</script>\n  </body>")
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
    js += INSTALL_GUARD
    APP_JS.write_text(js, encoding="utf-8")


def patch_prefetch_links() -> None:
    page_link = f'<link rel="prefetch" href="/assets/{PAGE_JS.name}">'
    data_link = f'<link rel="prefetch" href="/assets/{DATA_JS.name}">'
    for path in sorted(DIST.rglob("*.html")):
        html = path.read_text(encoding="utf-8")
        if page_link in html and data_link in html:
            continue
        marker = '<link rel="prefetch" href="/assets/sd3.html.1a4bf31e.js">'
        if marker in html:
            html = html.replace(marker, marker + data_link + page_link, 1)
            path.write_text(html, encoding="utf-8")


def _fast_ui_css_block() -> str:
    return f"""
{FAST_UI_CSS_MARKER}
.example-container > .right-container .anima-fast-credit {{
  margin: 0.55rem 0 0.65rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--sd-radius-md, 8px);
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--c-text-lighter, #606266);
  background: color-mix(in srgb, var(--el-color-success, #67c23a) 7%, var(--c-bg, #fff));
  border: 1px solid color-mix(in srgb, var(--el-color-success, #67c23a) 24%, var(--c-border, #dcdfe6));
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

body.anima-fast-page .example-container > .right-container > section:first-of-type {{
  flex: 0 0 auto;
}}

body.anima-fast-page .example-container > .right-container > section:first-of-type .el-scrollbar,
body.anima-fast-page .example-container > .right-container > section:first-of-type .el-scrollbar__wrap {{
  overflow: visible !important;
  max-height: none !important;
}}

.example-container > .right-container .anima-fast-intro-wrap {{
  padding-bottom: 0.25rem;
}}

.example-container > .right-container .anima-fast-guide-collapsible {{
  margin: 0.15rem 0 0.85rem;
}}

.example-container > .right-container .anima-fast-guide-toggle {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  width: auto;
  max-width: 100%;
  margin: 0;
  padding: 0.1rem 0;
  border: none;
  border-radius: 0;
  background: transparent;
  appearance: none;
  -webkit-appearance: none;
  color: var(--el-color-primary, #409eff);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  cursor: pointer;
  text-align: left;
  box-shadow: none;
}}

.example-container > .right-container .anima-fast-guide-toggle:hover {{
  color: var(--el-color-primary-dark-2, #337ecc);
  text-decoration: underline;
}}

.example-container > .right-container .anima-fast-guide-toggle:focus-visible {{
  outline: 2px solid color-mix(in srgb, var(--el-color-primary, #409eff) 45%, transparent);
  outline-offset: 2px;
}}

.example-container > .right-container .anima-fast-guide-toggle__icon {{
  flex: 0 0 auto;
  font-size: 11px;
  opacity: 0.85;
  transition: transform 0.15s ease;
}}

.example-container > .right-container .anima-fast-guide-collapsible.is-open .anima-fast-guide-toggle__icon {{
  transform: rotate(90deg);
}}

.example-container > .right-container .anima-fast-dataset-guide__body {{
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

.example-container > .right-container .anima-fast-dataset-guide__body p {{
  margin: 0.35rem 0;
}}

.example-container > .right-container .anima-fast-dataset-guide__body ul {{
  margin: 0.35rem 0 0.5rem 1.1rem;
  padding: 0;
}}

.example-container > .right-container .anima-fast-dataset-guide__body li {{
  margin: 0.2rem 0;
}}

.example-container > .right-container .anima-fast-dataset-guide__body code {{
  font-size: 12px;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--c-bg-mute, #fff);
  border: 1px solid var(--c-border, #e4e7ed);
}}

.example-container > .right-container .anima-fast-dataset-guide__highlight {{
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 10%, var(--c-bg, #fff));
  border: 1px solid color-mix(in srgb, var(--el-color-warning, #e6a23c) 28%, transparent);
}}

.example-container > .right-container .anima-fast-dataset-guide__note {{
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

html.dark .example-container > .right-container .anima-fast-dataset-guide__body {{
  background: color-mix(in srgb, var(--c-bg-light, #2d333b) 90%, var(--c-bg, #22272e));
  border-color: var(--c-border, #3d444d);
}}

html.dark .example-container > .right-container .anima-fast-dataset-guide__body code {{
  background: color-mix(in srgb, var(--c-bg, #22272e) 80%, transparent);
  border-color: var(--c-border, #3d444d);
}}

html.dark .example-container > .right-container .anima-fast-dataset-guide__highlight {{
  background: color-mix(in srgb, var(--el-color-warning, #e6a23c) 14%, var(--c-bg, #22272e));
}}

html.dark body.anima-fast-page .example-container .schema-container .el-collapse-item__header {{
  color: var(--c-text, #adbac7) !important;
  border-bottom-color: var(--c-border, #3d444d) !important;
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
        (GUIDE_CSS_MARKER in html, "dataset guide in html"),
        (CREDIT_CSS_MARKER in html, "open-source credit in html"),
        ("anima-fast-doc-links" in html, "doc tutorial link in html"),
        ("data-anima-fast-guide-toggle" in html, "collapsible guide toggle in html"),
        (FAST_UI_CSS_MARKER in POLISH_CSS.read_text(encoding="utf-8"), "fast ui css block"),
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
    assert_registered()
    print("patched Anima Fast frontend entry")


if __name__ == "__main__":
    main()
