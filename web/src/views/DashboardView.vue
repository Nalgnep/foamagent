<template>
  <div>
    <div class="page-head">
      <div><h2>仪表盘</h2><p>成都 B 线箱体发泡 · 在线感知 — 质量判定 — 工艺分析 — 建议 / 下发 — 效果验证 — 知识沉淀</p></div>
      <el-tag type="success" size="large">热成像一体机在线</el-tag>
    </div>
    <el-row :gutter="14" style="margin-bottom: 16px">
      <el-col :span="4" v-for="k in kpis" :key="k.label">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-top"><span :class="'kpi-tile ' + k.tile">{{ k.icon }}</span></div>
          <div class="kpi-label">{{ k.label }}</div>
          <div class="kpi-value">{{ k.value }}</div>
          <div class="kpi-sub">{{ k.sub }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14" style="margin-bottom: 14px">
      <el-col :span="9">
        <el-card header="智能体 · 根因分析">
          <template #header><span>智能体 · 根因分析</span><span style="float: right; color: #909399; font-size: 12px">候选根因来自知识库，非最终判定</span></template>
          <el-table :data="ngCases" empty-text="暂无 NG 案例">
            <el-table-column label="触发">
              <template #default="{ row }"><el-tag :type="row.grade === 'D' ? 'danger' : 'warning'">{{ row.grade === 'D' ? '高风险' : '人工发起' }}</el-tag></template>
            </el-table-column>
            <el-table-column label="根因候选">
              <template #default>{{ knowledge.slice(0, 2).map((k) => k.title).join('；') || '-' }}</template>
            </el-table-column>
            <el-table-column prop="box_barcode" label="箱体" />
            <el-table-column label="气泡">
              <template #default="{ row }">{{ row.max_bubble_mm }}mm / {{ row.bubble_count }}个</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="7">
        <el-card header="智能体 · 参数建议">
          <template #header><span>智能体 · 参数建议</span><el-button link style="float: right" @click="$emit('navigate', 'optimize', '参数建议报告')">根据快查</el-button></template>
          <div v-if="!sugs.length"><el-empty description="暂无参数建议" /></div>
          <el-card v-for="s in sugs.slice(0, 3)" :key="s.id" shadow="never" class="suggest-card">
            <div>建议 #{{ s.id }} · {{ s.box_barcode || '未关联箱体' }}
              <el-tag :type="s.confidence >= 0.7 ? 'success' : 'warning'">置信度 {{ Math.round(s.confidence * 100) }}%</el-tag>
            </div>
            <div style="color: #909399; font-size: 13px">
              料比 {{ s.suggested.material_ratio }} · 料温 {{ s.suggested.material_temp }}℃ ·
              模芯 {{ s.suggested.core_temp }}℃ · 固化 {{ s.suggested.curing_time }}s · 目标分 {{ s.objective_score }}
            </div>
            <div>
              <el-tag :type="s.feasible ? 'success' : 'danger'">{{ s.feasible ? '可行域内' : '超出可行域' }}</el-tag>
              <el-tag v-if="s.routed_to_llm" type="info">已转 LLM</el-tag>
              <span> · 状态 {{ s.status }}</span>
            </div>
          </el-card>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card header="质量率趋势">
          <template #header><span>质量率趋势</span><span style="float: right; color: #909399; font-size: 12px">按检测序列累计</span></template>
          <p class="legend"><span><i style="background:#16a34a"></i>OK率</span><span><i style="background:#f59e0b"></i>RISK率</span><span><i style="background:#dc2626"></i>NG率</span></p>
          <TrendChart :thermals="thermals" />
          <p style="color: #909399; font-size: 13px">样本 {{ thermals.length }} 台 · 当前一次合格率 {{ (dashboard.kpis.first_pass_rate * 100).toFixed(1) }}%（演示数据）</p>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14">
      <el-col :span="15">
        <el-card header="当前箱体">
          <template #header><span>当前箱体</span><span style="float: right; color: #909399; font-size: 12px">最新一条记录</span></template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="时间">{{ latestBox.created_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="箱体">{{ latestBox.barcode || '-' }} · 夹具 {{ latestBox.fixture_no || '-' }} · {{ latestBox.product || '-' }}</el-descriptions-item>
            <el-descriptions-item label="热成像">
              {{ latestThermal.grade || '-' }} · {{ latestThermal.max_bubble_mm ?? '-' }}mm · {{ latestThermal.bubble_count ?? '-' }}个
              <el-tag :type="latestThermal.is_ng ? 'warning' : 'success'">{{ latestThermal.is_ng ? 'RISK' : 'OK' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="最新建议">
              <template v-if="latestSug.id">#{{ latestSug.id }} · 置信度 {{ Math.round(latestSug.confidence * 100) }}% · 缺陷概率 {{ latestSug.defect_probability }}</template>
              <template v-else>暂无</template>
            </el-descriptions-item>
            <el-descriptions-item label="产线">模式 {{ systemState.mode }} · {{ systemState.stopped ? '已停止' : '正常' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="9">
        <el-card header="本班判定分布">
          <template #header><span>本班判定分布</span><span style="float: right; color: #909399; font-size: 12px">共 {{ thermals.length }} 台</span></template>
          <DonutChart :ok="okCount" :risk="riskCount" :ng="ngCount" />
          <p>OK <b>{{ okCount }}</b> · {{ pct(okCount) }} ｜ RISK <b>{{ riskCount }}</b> · {{ pct(riskCount) }} ｜ NG <b>{{ ngCount }}</b> · {{ pct(ngCount) }}</p>
          <p style="color: #909399; font-size: 13px">OK 为 A/B 且非 NG；RISK 为 C 且非 NG；NG 为热成像 NG 判定。</p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import TrendChart from '../components/TrendChart.vue'
import DonutChart from '../components/DonutChart.vue'

defineEmits(['navigate'])
const dashboard = ref({ kpis: { first_pass_rate: 1 } })
const systemState = ref({ mode: '-', stopped: false })
const thermals = ref([])
const exceptions = ref([])
const boxes = ref([])
const sugs = ref([])
const knowledge = ref([])

const openExc = computed(() => exceptions.value.filter((e) => e.status === '待确认/关联异常'))
const resolvedExc = computed(() => exceptions.value.filter((e) => e.status !== '待确认/关联异常'))
const unreviewedNG = computed(() => thermals.value.filter((t) => t.is_ng && !t.reviewed_by))
const reviewed = computed(() => thermals.value.filter((t) => t.reviewed_by))
const todayCount = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return thermals.value.filter((t) => (t.created_at || '').slice(0, 10) === today).length
})
const kpis = computed(() => [
  { icon: '☑', tile: 'teal', label: '我的待办', value: openExc.value.length + unreviewedNG.value.length, sub: '异常待确认 + 未复核 NG' },
  { icon: '🔥', tile: 'red', label: '紧急待办', value: unreviewedNG.value.length, sub: '未复核 NG 箱体' },
  { icon: '⚠', tile: 'amber', label: '待处理异常', value: openExc.value.length, sub: '追溯异常队列' },
  { icon: '✓', tile: 'green', label: '当班已处理', value: resolvedExc.value.length + reviewed.value.length, sub: '已修正异常 + 已复核' },
  { icon: '📷', tile: 'blue', label: '今日检测', value: todayCount.value, sub: '按检测日期统计（演示库）' },
  { icon: '🗄', tile: 'purple', label: '累计检测', value: thermals.value.length, sub: '演示库检测总数' }
])
const ngCases = computed(() => thermals.value.filter((t) => t.is_ng).slice(0, 5))
const okCount = computed(() => thermals.value.filter((t) => (t.grade === 'A' || t.grade === 'B') && !t.is_ng).length)
const riskCount = computed(() => thermals.value.filter((t) => t.grade === 'C' && !t.is_ng).length)
const ngCount = computed(() => thermals.value.filter((t) => t.is_ng).length)
const latestBox = computed(() => boxes.value[0] || {})
const latestThermal = computed(() => thermals.value[0] || {})
const latestSug = computed(() => sugs.value[0] || {})
function pct(n) {
  const total = thermals.value.length || 1
  return (n / total * 100).toFixed(1) + '%'
}

onMounted(async () => {
  try {
    const [d, st, th, ex, bx, sg, kn] = await Promise.all([
      api('/api/dashboard'), api('/api/system/state'), api('/api/thermal-results'),
      api('/api/trace/exceptions'), api('/api/boxes'), api('/api/suggestions'), api('/api/knowledge')
    ])
    dashboard.value = d; systemState.value = st; thermals.value = th
    exceptions.value = ex; boxes.value = bx; sugs.value = sg; knowledge.value = kn
  } catch (e) { ElMessage.error(e.message) }
})
</script>
