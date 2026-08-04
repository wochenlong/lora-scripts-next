<script setup lang="ts">
import { computed } from "vue"

interface LossSeries {
  name: string
  color: string
  points: { step: number; value: number }[]
}

const props = defineProps<{ series: LossSeries[] }>()

const WIDTH = 600
const HEIGHT = 240
const PAD = { top: 14, right: 14, bottom: 24, left: 52 }

const domain = computed(() => {
  const all = props.series.flatMap((item) => item.points)
  if (!all.length) return { minX: 0, maxX: 1, minY: 0, maxY: 1 }
  const minX = Math.min(...all.map((p) => p.step))
  const rawMaxX = Math.max(...all.map((p) => p.step))
  const minY = Math.min(...all.map((p) => p.value))
  const rawMaxY = Math.max(...all.map((p) => p.value))
  return {
    minX,
    maxX: rawMaxX === minX ? minX + 1 : rawMaxX,
    minY,
    maxY: rawMaxY === minY ? minY + 1 : rawMaxY,
  }
})

function path(points: { step: number; value: number }[]): string {
  const { minX, maxX, minY, maxY } = domain.value
  return points.map((p, index) => {
    const x = PAD.left + ((p.step - minX) / (maxX - minX)) * (WIDTH - PAD.left - PAD.right)
    const y = PAD.top + (1 - (p.value - minY) / (maxY - minY)) * (HEIGHT - PAD.top - PAD.bottom)
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(" ")
}

function latest(item: LossSeries): string {
  const point = item.points[item.points.length - 1]
  return point ? point.value.toPrecision(4) : "-"
}

function formatTick(value: number): string {
  return Math.abs(value) < 0.01 ? value.toExponential(1) : String(Number(value.toPrecision(3)))
}
</script>

<template>
  <div class="loss-chart">
    <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img">
      <line :x1="PAD.left" :y1="PAD.top" :x2="PAD.left" :y2="HEIGHT - PAD.bottom" class="axis" />
      <line :x1="PAD.left" :y1="HEIGHT - PAD.bottom" :x2="WIDTH - PAD.right" :y2="HEIGHT - PAD.bottom" class="axis" />
      <text :x="4" :y="PAD.top + 8" class="tick">{{ formatTick(domain.maxY) }}</text>
      <text :x="4" :y="HEIGHT - PAD.bottom" class="tick">{{ formatTick(domain.minY) }}</text>
      <text :x="PAD.left" :y="HEIGHT - 6" class="tick">{{ domain.minX }}</text>
      <text :x="WIDTH - PAD.right" :y="HEIGHT - 6" class="tick" text-anchor="end">{{ domain.maxX }}</text>
      <path v-for="item in series" :key="item.name" :d="path(item.points)" :stroke="item.color" class="line" />
    </svg>
    <div class="loss-legend">
      <span v-for="item in series" :key="item.name"><i :style="{ background: item.color }"></i>{{ item.name }} <b>{{ latest(item) }}</b></span>
    </div>
  </div>
</template>
