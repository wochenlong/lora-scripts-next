"""Shared HTML/CSS for 帮助 → 新手上路 (keep patch scripts in sync)."""

GUIDE_ANIMA_EDIT_ANCHOR = "anima-edit-dataset"
GUIDE_ANIMA_EDIT_URL = f"/help/guide.html#{GUIDE_ANIMA_EDIT_ANCHOR}"

GUIDE_MASCOT_V = "20260525-nt5"

GUIDE_HTML_BODY = f"""<div class="sd-guide"><div class="sd-guide-pager"><input type="radio" name="sd-guide-page" id="sd-guide-p1" class="sd-guide-pager__input" checked><input type="radio" name="sd-guide-page" id="sd-guide-p2" class="sd-guide-pager__input"><nav class="sd-guide-pager__nav" aria-label="新手上路分页"><label for="sd-guide-p1" class="sd-guide-pager__tab">① 新手上路</label><label for="sd-guide-p2" class="sd-guide-pager__tab">② 图像编辑数据集</label></nav><div class="sd-guide-pager__panels"><div class="sd-guide-pager__panel sd-guide-pager__panel--1"><div class="sd-guide-intro"><div class="sd-guide-intro__art" aria-hidden="true"><img src="/assets/guide-mascot.webp?v={GUIDE_MASCOT_V}" alt="" loading="lazy" decoding="async"></div><div class="sd-guide-intro__body"><h2 id="新手上路" tabindex="-1"><a class="header-anchor" href="#新手上路" aria-hidden="true">#</a> 新手上路</h2><ol><li><strong>准备数据</strong>：训练图片 + 同名 <code>.txt</code> 标签；可用「工具与调试 → 数据集打标」。</li><li><strong>选择训练类型</strong>（侧栏「训练」）：<ul><li><a href="/lora/sd3.html"><strong>Anima</strong></a> — 文生图 LoRA（推荐）</li><li><a href="/lora/anima-edit.html"><strong>Anima Edit</strong></a> — 图像编辑（Target + Reference）</li><li><a href="/lora/flux.html"><strong>Flux</strong></a></li><li><a href="/lora/master.html"><strong>Stable Diffusion</strong></a> — 默认 SDXL</li><li><a href="/dreambooth/index.html"><strong>Dreambooth 训练</strong></a></li></ul></li><li><strong>图像编辑数据集</strong>：见本页 <a href="{GUIDE_ANIMA_EDIT_URL}">② 图像编辑数据集</a> 示意图。</li><li><strong>填写参数并开训</strong>：中栏表单 → 右栏「开始训练」。</li><li><strong>查看进度</strong>：<a href="/monitor/" target="_blank" rel="noopener noreferrer">训练监控</a>、<a href="/tensorboard/">Tensorboard</a>。</li></ol></div></div><section class="sd-guide-migrate"><h2 id="从秋叶版迁移" tabindex="-1"><a class="header-anchor" href="#从秋叶版迁移" aria-hidden="true">#</a> 从秋叶版迁移</h2><p>若你使用过 <strong>Akegarasu/lora-scripts</strong>（秋叶一键包），本版主要变化：</p><ul><li><strong>品牌</strong>：项目名 <strong>lora-scripts-next</strong> / Next Trainer，侧栏按「训练 / 工具 / 帮助 / 其他」分组。</li><li><strong>导航</strong>：LoRA 下为 Anima、<strong>Anima Edit</strong>、Flux、Stable Diffusion；SD1.5 精简页：<a href="/lora/basic.html">/lora/basic.html</a>。</li><li><strong>Anima</strong>：原 SD3 入口改为 Anima（Qwen + T5 + DiT）。</li><li><strong>监控</strong>：独立 <a href="/monitor/" target="_blank" rel="noopener noreferrer">训练监控页</a>、Loss 曲线、<code>/train-log</code> 日志流。</li><li>更多版本说明见 <a href="/other/changelog.html">更新日志</a>。</li></ul></section></div><div class="sd-guide-pager__panel sd-guide-pager__panel--2"><section class="sd-guide-dataset" id="{GUIDE_ANIMA_EDIT_ANCHOR}"><h2 tabindex="-1"><a class="header-anchor" href="#{GUIDE_ANIMA_EDIT_ANCHOR}" aria-hidden="true">#</a> Anima Edit · 数据集怎么放</h2><p>训练需要<strong>两个目录</strong>：目标图 <code>target/</code> 与参考图 <code>reference/</code>。在 Anima Edit 训练页分别填入「目标图目录」「参考图目录」。</p><p>左侧「参考图布局」选<strong>单张参考图</strong>或<strong>双张参考图</strong>，目录结构不同：</p><div class="sd-guide-dataset__block"><h3>单张参考图</h3><p class="sd-guide-dataset__hint">参考根目录下与 target <strong>同名</strong> 一张图（如 <code>target/a.png</code> → <code>reference/a.png</code>）。标签 <code>.txt</code> / <code>.json</code> 放在 target 侧。</p><pre class="sd-guide-dataset__tree">my_dataset/
├── target/              ← 表单「目标图目录」
│   ├── a.png
│   ├── a.txt
│   └── b.png
└── reference/           ← 表单「参考图目录」
    ├── a.png            （与 target 同名）
    └── b.png</pre></div><div class="sd-guide-dataset__block"><h3>双张参考图</h3><p class="sd-guide-dataset__hint">每个样本在 reference 下建<strong>与 target 文件名同名的文件夹</strong>，里面放 2 张图（按文件名排序取前 2 张）。</p><pre class="sd-guide-dataset__tree">my_dataset/
├── target/              ← 表单「目标图目录」
│   ├── a.png
│   └── a.txt
└── reference/           ← 表单「参考图目录」
    └── a/               ← 文件夹名 = target 文件名（无扩展名）
        ├── 1.png
        └── 2.png</pre></div><p class="sd-guide-dataset__foot">文生图 LoRA 请用侧栏「Anima」页；仅图像编辑使用 Anima Edit。</p><p><a class="sd-home-portal sd-home-portal--primary" href="/lora/anima-edit.html"><span class="sd-home-portal__title">返回 Anima Edit 训练页</span><span class="sd-home-portal__desc">填写路径并开始训练</span></a></p></section></div></div></div></div>"""

GUIDE_HASH_SCRIPT = f"""<script>(function(){{function a(){{if(location.hash!=="#{GUIDE_ANIMA_EDIT_ANCHOR}")return;var r=document.getElementById("sd-guide-p2");if(r)r.checked=true;}}a();window.addEventListener("hashchange",a);}})();</script>"""

GUIDE_PAGER_CSS = """
/* 新手上路 · 翻页 */
main.page .theme-default-content .sd-guide-pager__input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
main.page .theme-default-content .sd-guide-pager__nav {
  display: flex;
  gap: 0.5rem;
  margin: 0 0 1rem;
  flex-wrap: wrap;
}
main.page .theme-default-content .sd-guide-pager__tab {
  flex: 1;
  min-width: 8rem;
  padding: 0.45rem 0.75rem;
  text-align: center;
  font-size: 0.875rem;
  font-weight: 500;
  border: 1px solid var(--c-border, #e4e7ed);
  border-radius: 8px;
  cursor: pointer;
  color: var(--c-text, #303133);
  background: var(--c-bg-soft, #f5f7fa);
  transition: border-color 0.15s, background 0.15s;
}
main.page .theme-default-content .sd-guide-pager__tab:hover {
  border-color: var(--el-color-primary, #409eff);
}
main.page .theme-default-content #sd-guide-p1:checked ~ .sd-guide-pager__nav label[for="sd-guide-p1"],
main.page .theme-default-content #sd-guide-p2:checked ~ .sd-guide-pager__nav label[for="sd-guide-p2"] {
  border-color: var(--el-color-primary, #409eff);
  background: color-mix(in srgb, var(--el-color-primary, #409eff) 12%, transparent);
  color: var(--el-color-primary, #409eff);
}
main.page .theme-default-content .sd-guide-pager__panel {
  display: none;
}
main.page .theme-default-content #sd-guide-p1:checked ~ .sd-guide-pager__panels .sd-guide-pager__panel--1,
main.page .theme-default-content #sd-guide-p2:checked ~ .sd-guide-pager__panels .sd-guide-pager__panel--2 {
  display: block;
}
/* 数据集示意图 */
main.page .theme-default-content .sd-guide-dataset__block {
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border: 1px solid var(--c-border, #e4e7ed);
  border-radius: 10px;
  background: var(--c-bg-soft, #fafafa);
}
main.page .theme-default-content .sd-guide-dataset__block h3 {
  margin: 0 0 0.35rem;
  font-size: 1rem;
}
main.page .theme-default-content .sd-guide-dataset__hint {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  color: var(--c-text-lighter, #606266);
}
main.page .theme-default-content .sd-guide-dataset__tree {
  margin: 0;
  padding: 0.65rem 0.85rem;
  font-size: 0.75rem;
  line-height: 1.45;
  border-radius: 6px;
  background: var(--c-bg, #fff);
  border: 1px dashed var(--c-border, #dcdfe6);
  overflow-x: auto;
  white-space: pre;
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
}
main.page .theme-default-content .sd-guide-dataset__foot {
  font-size: 0.8125rem;
  color: var(--c-text-lighter, #909399);
}
main.page .theme-default-content .sd-guide-dataset .sd-home-portal {
  display: block;
  margin-top: 1rem;
  text-decoration: none;
}
"""

EDIT_GUIDE_PORTAL_CSS = """
/* Anima Edit 专家区 → 帮助页数据集说明 */
main.page .theme-default-content .sd-edit-guide-portal-wrap {
  margin: 0.75rem 0 0;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary, #409eff) 35%, transparent);
  background: color-mix(in srgb, var(--el-color-primary, #409eff) 8%, var(--c-bg, #fff));
}
main.page .theme-default-content a.sd-edit-guide-portal {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--el-color-primary, #409eff);
  text-decoration: none;
}
main.page .theme-default-content a.sd-edit-guide-portal:hover {
  text-decoration: underline;
}
main.page .theme-default-content .sd-edit-guide-portal__hint {
  margin: 0.35rem 0 0;
  font-size: 0.8125rem;
  color: var(--c-text-lighter, #909399);
  line-height: 1.5;
}
"""
