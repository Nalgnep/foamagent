<template>
  <svg viewBox="0 0 140 140" width="150" height="150">
    <circle cx="70" cy="70" r="54" fill="none" stroke="#eef2f5" stroke-width="18" />
    <circle
      v-for="seg in segments"
      :key="seg.label"
      cx="70" cy="70" r="54" fill="none"
      :stroke="seg.color" stroke-width="18" stroke-linecap="round"
      :stroke-dasharray="`${seg.len.toFixed(1)} ${(C - seg.len).toFixed(1)}`"
      :stroke-dashoffset="(-seg.offset).toFixed(1)"
      transform="rotate(-90 70 70)"
    />
    <text x="70" y="66" text-anchor="middle" font-size="20" font-weight="700">{{ total }}</text>
    <text x="70" y="84" text-anchor="middle" font-size="11" fill="#64748b">本班已检</text>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  ok: { type: Number, default: 0 },
  risk: { type: Number, default: 0 },
  ng: { type: Number, default: 0 }
})
const C = 2 * Math.PI * 54
const total = computed(() => props.ok + props.risk + props.ng || 1)
const segments = computed(() => {
  let off = 0
  return [
    { label: 'OK', n: props.ok, color: '#16a34a' },
    { label: 'RISK', n: props.risk, color: '#f59e0b' },
    { label: 'NG', n: props.ng, color: '#dc2626' }
  ].map((s) => {
    const len = (s.n / total.value) * C
    const seg = { ...s, len, offset: off }
    off += len
    return seg
  })
})
</script>
