<template>
  <svg v-if="seq.length" class="trend-chart" viewBox="0 0 300 120" width="100%" height="150">
    <line x1="10" y1="35" x2="290" y2="35" stroke="#eef2f5" />
    <line x1="10" y1="60" x2="290" y2="60" stroke="#eef2f5" />
    <line x1="10" y1="85" x2="290" y2="85" stroke="#eef2f5" />
    <line x1="10" y1="10" x2="10" y2="110" stroke="#e2e8f0" />
    <line x1="10" y1="110" x2="290" y2="110" stroke="#e2e8f0" />
    <polyline :points="ptsOK" fill="none" stroke="#16a34a" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
    <polyline :points="ptsRisk" fill="none" stroke="#f59e0b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
    <polyline :points="ptsNG" fill="none" stroke="#dc2626" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
  <el-empty v-else description="暂无检测序列" />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ thermals: { type: Array, default: () => [] } })
const seq = computed(() => [...props.thermals].reverse())

function points(kind) {
  let cumNG = 0
  let cumC = 0
  return seq.value.map((t, i) => {
    cumNG += t.is_ng ? 1 : 0
    cumC += t.grade === 'C' && !t.is_ng ? 1 : 0
    const x = seq.value.length === 1 ? 150 : 10 + (i * 280) / (seq.value.length - 1)
    const rate = kind === 'ng' ? cumNG / (i + 1)
      : kind === 'risk' ? cumC / (i + 1)
      : 1 - cumNG / (i + 1)
    return `${x.toFixed(1)},${(110 - rate * 100).toFixed(1)}`
  }).join(' ')
}
const ptsNG = computed(() => points('ng'))
const ptsRisk = computed(() => points('risk'))
const ptsOK = computed(() => points('ok'))
</script>
