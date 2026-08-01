<script setup lang="ts">
const portals = [
  { title: "训练", text: "基础模型 × 训练引擎 × 训练目标，一处完成配置与提交。", to: "/training", tone: "blue" },
  { title: "数据集", text: "标签编辑与模型打标，准备训练所需的 caption。", to: "/dataset/editor", tone: "violet" },
  { title: "任务", text: "查看训练任务状态、日志入口与运行监控。", to: "/tasks", tone: "cyan" },
] as const
</script>

<template>
  <div class="home-page">
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">LOCAL TRAINING WORKSPACE</span>
        <h1>模型训练，从一套清晰的工作流开始。</h1>
        <p>LoRA Scripts Next 将训练配置、数据集准备与运行监控集中在本地界面中。</p>
        <div class="hero-actions"><RouterLink class="primary-action" to="/training">开始配置训练</RouterLink><RouterLink class="secondary-action" to="/help/guide.html">阅读使用指南</RouterLink></div>
      </div>
      <div class="hero-visual"><div class="visual-grid" /><div class="orbit orbit-one" /><div class="orbit orbit-two" /><img src="/assets/home-logo.webp" alt="LoRA Scripts Next"></div>
    </section>
    <section class="portal-grid" aria-label="功能入口">
      <RouterLink v-for="(portal, index) in portals" :key="portal.to" :to="portal.to" class="portal-card" :data-tone="portal.tone">
        <span class="portal-index">0{{ index + 1 }}</span><h2>{{ portal.title }}</h2><p>{{ portal.text }}</p><span class="portal-link">进入工作区 <b>→</b></span>
      </RouterLink>
    </section>
    <section class="status-strip"><span><i class="status-dot" /> 本地服务架构</span><span>Vue 3 训练工作区</span><span>Stable Diffusion · Flux · Anima</span></section>
  </div>
</template>
