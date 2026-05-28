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

ROUTE_KEY = "v-anima-fast"
PAGE_TITLE = "Anima Fast LoRA"
TRAIN_TYPE = "anima-lora-fast"

GUARD_PATTERN = re.compile(
    r";?\(\(\)=>\{if\(window\.__ANIMA_FAST_INSTALL_GUARD__\).*?setTimeout\(status,0\)\}\)\(\);",
    re.DOTALL,
)

INSTALL_GUARD = r''';(()=>{if(window.__ANIMA_FAST_INSTALL_GUARD__)return;window.__ANIMA_FAST_INSTALL_GUARD__=true;let last={feature_enabled:false,state:"unknown"},es=null,tmr=null,scheduled=false;function q(s){return Array.from(document.querySelectorAll(s))}function isFastPage(){return location.pathname==="/lora/anima-fast.html"||location.pathname==="/lora/anima-fast"||location.pathname==="/lora/anima-fast.md"}function setFastLinksVisible(v){q('a[href="/lora/anima-fast.md"],a[href="/lora/anima-fast.html"],a[href="/lora/anima-fast"]').forEach(a=>{const li=a.closest("li");(li||a).style.display=v?"":"none"})}function setControls(d){if(!isFastPage())return;const enabled=!!d.feature_enabled,working=d.state==="installing"||d.state==="auditing",ready=d.state==="ready";q("[data-anima-fast-install]").forEach(b=>{b.disabled=!enabled||working;b.setAttribute("aria-disabled",b.disabled?"true":"false")});q(".right-container button").forEach(b=>{const t=(b.textContent||"").trim();if(t==="开始训练"||t==="✨加载训练预设✨"||t==="导入配置文件"||t==="保存参数")b.disabled=!enabled||!ready});document.body.classList.toggle("anima-fast-disabled",!enabled||!ready)}function label(d){if(!d.feature_enabled)return"已禁用";return d.state==="ready"?"已安装并通过审计":d.state==="installing"?"安装中":d.state==="auditing"?"审计中":d.state==="broken"?"安装/审计失败":d.state==="installed_unverified"?"已复制，等待审计":d.state==="not_installed"?"未安装":d.state||"未知状态"}function appendLog(x){const p=document.querySelector("[data-anima-fast-log]");if(!p)return;p.hidden=false;p.textContent+=(p.textContent?"\n":"")+x;p.scrollTop=p.scrollHeight}function apply(d){last=d||last;const enabled=!!last.feature_enabled;setFastLinksVisible(enabled);setControls(last);const n=document.querySelector("[data-anima-fast-status]");if(n)n.textContent=label(last);const a=last.facts&&last.facts.audit;if(a&&!a.ok&&a.errors)appendLog("[audit] "+a.errors.join("; "))}async function status(){try{const r=await fetch("/api/plugins/anima-lora/status"),j=await r.json();apply(j.data||{feature_enabled:false,state:"unknown"})}catch(e){const n=document.querySelector("[data-anima-fast-status]");if(n)n.textContent="状态检查失败"}}function scheduleStatus(){if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;status()},120)}function openLog(url){if(!url||!window.EventSource)return;if(es)es.close();appendLog("[log] streaming "+url);es=new EventSource(url);es.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.text)appendLog(d.text);if(d.done){appendLog("[log] done");es.close();es=null;if(tmr){clearInterval(tmr);tmr=null}status()}}catch(_){appendLog(e.data)}};es.onerror=()=>{appendLog("[log] stream disconnected");if(es){es.close();es=null}status()}}document.addEventListener("click",async e=>{const b=e.target&&e.target.closest&&e.target.closest("[data-anima-fast-install]");if(!b)return;if(!last.feature_enabled)return;b.disabled=true;const s=document.querySelector("[data-anima-fast-status]"),p=document.querySelector("[data-anima-fast-log]");if(p){p.hidden=false;p.textContent=""}if(s)s.textContent="安装任务启动中";try{const r=await fetch("/api/plugins/anima-lora/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dry_run:false})}),j=await r.json();if(j.status!=="success"){if(s)s.textContent=j.message||"安装失败";appendLog("[error] "+(j.message||"install failed"));return}const d=j.data||{};if(s)s.textContent="安装中";appendLog("[task] "+(d.task_id||"unknown"));openLog(d.log_stream||d.log_stream_url||(d.task_id?"/api/plugins/anima-lora/install/log/stream/"+d.task_id:""));if(tmr)clearInterval(tmr);tmr=setInterval(status,2000);status()}catch(t){if(s)s.textContent="安装失败";appendLog("[error] "+t)}finally{setTimeout(()=>setControls(last),250)}});new MutationObserver(scheduleStatus).observe(document.documentElement,{childList:true,subtree:true});document.addEventListener("DOMContentLoaded",status);setTimeout(status,0)})();'''


def write_page_chunks() -> None:
    page = (
        'import{_ as s,o as t,c as o,a as e,b as a}from"./app.547295de.js";'
        "const _={},"
        'c=e("h1",{id:"anima-fast-lora",tabindex:"-1"},['
        'e("a",{class:"header-anchor",href:"#anima-fast-lora","aria-hidden":"true"},"#"),'
        'a(" Anima Fast LoRA")],-1),'
        'n=e("p",null,"Anima LoRA Fast 独立后端训练入口",-1),'
        'd=e("p",null,"使用独立 runtime、专属参数、兼容的训练监控与输出目录。",-1),'
        'm=e("div",{class:"anima-fast-install-panel",style:"display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0;"},['
        'e("button",{"data-anima-fast-install":"",type:"button",class:"el-button el-button--primary is-plain"},['
        'e("span",null,"安装/修复 Anima Fast 拓展")]),'
        'e("span",{"data-anima-fast-status":"",style:"font-size:13px;opacity:.8;"},"检查中")],-1),'
        'f=e("pre",{"data-anima-fast-log":"",hidden:"",style:"max-height:260px;overflow:auto;margin:12px 0;padding:10px;border:1px solid var(--c-border);border-radius:6px;font-size:12px;line-height:1.45;white-space:pre-wrap;"},null,-1),'
        "l=[c,n,d,m,f];"
        'function i(h,u){return t(),o("div",null,l)}'
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
    html = html.replace("Anima Stable Diffusion LoRA | SD 训练 UI", "Anima Fast LoRA | SD 训练 UI")
    html = html.replace("/assets/sd3.html.1a4bf31e.js", f"/assets/{PAGE_JS.name}")
    html = html.replace("/assets/sd3.html.eaeb05e1.js", f"/assets/{DATA_JS.name}")
    html = html.replace(
        '<main><div><h1 id="sd3-训练-专家模式" tabindex="-1"><a class="header-anchor" href="#sd3-训练-专家模式" aria-hidden="true">#</a> Anima Stable Diffusion LoRA</h1><p>Anima DiT 模型 LoRA 训练 专家模式</p><p>Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数</p></div></main>',
        '<main><div><h1 id="anima-fast-lora" tabindex="-1"><a class="header-anchor" href="#anima-fast-lora" aria-hidden="true">#</a> Anima Fast LoRA</h1><p>Anima LoRA Fast 独立后端训练入口</p><p>使用独立 runtime、专属参数、兼容的训练监控与输出目录。</p><div class="anima-fast-install-panel" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0;"><button data-anima-fast-install type="button" class="el-button el-button--primary is-plain"><span>安装/修复 Anima Fast 拓展</span></button><span data-anima-fast-status style="font-size:13px;opacity:.8;">检查中</span></div><pre data-anima-fast-log hidden style="max-height:260px;overflow:auto;margin:12px 0;padding:10px;border:1px solid var(--c-border);border-radius:6px;font-size:12px;line-height:1.45;white-space:pre-wrap;"></pre></div></main>',
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
        '["v-0dc76a3b","/lora/sd3.html",{title:"SD3 \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},["/lora/sd3","/lora/sd3.md"]],["v-anima-fast","/lora/anima-fast.html",{title:"Anima Fast LoRA"},["/lora/anima-fast","/lora/anima-fast.md"]]',
    )
    js = _replace_once(
        js,
        '{"text":"Anima","link":"/lora/sd3.md"},{"text":"Flux","link":"/lora/flux.md"}',
        '{"text":"Anima","link":"/lora/sd3.md"},{"text":"Anima Fast","link":"/lora/anima-fast.md"},{"text":"Flux","link":"/lora/flux.md"}',
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
    ]
    missing = [label for ok, label in checks if not ok]
    if missing:
        raise RuntimeError("Anima Fast frontend patch incomplete: " + ", ".join(missing))


def main() -> None:
    write_page_chunks()
    patch_html()
    patch_app_js()
    patch_prefetch_links()
    assert_registered()
    print("patched Anima Fast frontend entry")


if __name__ == "__main__":
    main()
