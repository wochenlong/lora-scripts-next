<template>
  <article class="content-page">
    <header class="content-hero content-hero-split"><div><span class="eyebrow">GETTING STARTED</span><h1>新手上路</h1><p>从准备图片到查看训练结果，按顺序完成一次本地训练。</p></div><img src="/assets/guide-mascot.webp" alt="LoRA Scripts Next 使用指南"></header>
    <section><h2>1. 准备数据</h2><p>准备训练图片及同名 <code>.txt</code> 标签文件。没有标签时可先使用 <RouterLink to="/dataset/tagger">数据集打标</RouterLink>，再到 <RouterLink to="/dataset/editor">标签编辑器</RouterLink>清理 Caption。</p></section>
    <section><h2>2. 选择训练类型</h2><div class="content-cards"><div><h3>LoRA 训练</h3><p><RouterLink to="/training">训练页</RouterLink>中选择基础模型、训练引擎与训练目标：Anima DiT、Flux 或 SD / SDXL，搭配 Kohya-ss 或 Anima Fast。</p></div><div><h3>全量微调</h3><p><RouterLink to="/training?model=anima&engine=kohya&target=finetune">Anima 全量微调</RouterLink>用于 DiT 整模微调；<RouterLink to="/dreambooth/index.html">Dreambooth</RouterLink>用于 Stable Diffusion 全量训练。</p></div></div></section>
    <section><h2>3. 填写参数并训练</h2><ol><li>选择底模、图片目录和输出目录。</li><li>选择训练预设或按需调整参数，右侧会实时生成 TOML 预览。</li><li>先执行参数校验，再点击“开始训练”并确认创建后台任务。</li></ol></section>
    <section><h2>4. 查看进度</h2><p>提交后可打开训练日志，也可进入 <RouterLink to="/tasks">训练任务</RouterLink>终止任务；指标与曲线在 <RouterLink to="/tensorboard.html">TensorBoard</RouterLink> 中查看。</p></section>
    <section><h2>从秋叶版迁移</h2><ul><li>训练类型现在按 LoRA 与全量微调组织，旧 URL 仍保持兼容。</li><li>Anima 标准、Fast 和 Finetune 使用各自独立的 Schema 与约束。</li><li>历史配置与自动草稿继续使用旧浏览器 storage key。</li></ul></section>
  </article>
</template>
