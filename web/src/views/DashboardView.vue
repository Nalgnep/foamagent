<template>
  <div class="view-stack">
    <div class="page-head">
      <div><h2>仪表盘</h2><p>成都 B 线箱体发泡 · 在线感知 — 质量判定 — 工艺分析 — 建议 / 下发 — 效果验证 — 知识沉淀</p></div>
      <el-tag type="success" size="large">热成像一体机在线</el-tag>
    </div>
    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="4" v-for="k in kpis" :key="k.label">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-top"><span :class="'kpi-tile ' + k.tile">{{ k.icon }}</span></div>
          <div class="kpi-label">{{ k.label }}</div>
          <div class="kpi-value">{{ k.value }}</div>
          <div class="kpi-sub">{{ k.sub }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="14">
        <el-card>
          <template #header><div class="panel-head"><span>智能体 · 根因分析</span><span class="sub">候选根因来自知识库，非最终判定</span></div></template>
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
      <el-col :span="10">
        <el-card>
          <template #header><div class="panel-head"><span>智能体 · 参数建议</span><el-button link @click="$emit('navigate', 'optimize', '参数建议报告')">根据快查</el-button></div></template>
          <div v-if="!sugs.length"><el-empty description="暂无参数建议" /></div>
          <div v-for="s in sugs.slice(0, 3)" :key="s.id" class="suggest-item">
            <div class="t"><span>建议 #{{ s.id }} · {{ s.box_barcode || '未关联箱体' }}</span>
              <el-tag :type="s.confidence >= 0.7 ? 'success' : 'warning'">置信度 {{ Math.round(s.confidence * 100) }}%</el-tag>
            </div>
            <div class="p">
              料比 {{ s.suggested.material_ratio }} · 料温 {{ s.suggested.material_temp }}℃ ·
              模芯 {{ s.suggested.core_temp }}℃ · 固化 {{ s.suggested.curing_time }}s · 目标分 {{ s.objective_score }}
            </div>
            <div>
              <el-tag :type="s.feasible ? 'success' : 'danger'">{{ s.feasible ? '可行域内' : '超出可行域' }}</el-tag>
              <el-tag v-if="s.routed_to_llm" type="info">已转 LLM</el-tag>
              <span> · 状态 {{ s.status }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="14">
        <el-card>
          <template #header><div class="panel-head"><span>质量率趋势</span><span class="sub">按检测序列累计</span></div></template>
          <p class="legend"><span><i style="background:#16a34a"></i>OK率</span><span><i style="background:#f59e0b"></i>RISK率</span><span><i style="background:#dc2626"></i>NG率</span></p>
          <TrendChart :thermals="thermals" />
          <p class="card-note" style="margin: 12px 0 0">样本 {{ thermals.length }} 台 · 当前一次合格率 {{ (dashboard.kpis.first_pass_rate * 100).toFixed(1) }}%（演示数据）</p>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-card>
          <template #header><div class="panel-head"><span>当前箱体</span><span class="sub">最新一条记录</span></div></template>
          <div class="info-grid">
            <div class="info-item"><div class="k">时间</div><div class="v">{{ latestBox.created_at || '-' }}</div></div>
            <div class="info-item"><div class="k">箱体 / 夹具 / 产品</div><div class="v">{{ latestBox.barcode || '-' }} · {{ latestBox.fixture_no || '-' }} · {{ latestBox.product || '-' }}</div></div>
            <div class="info-item"><div class="k">热成像</div><div class="v">{{ latestThermal.grade || '-' }} · {{ latestThermal.max_bubble_mm ?? '-' }}mm · {{ latestThermal.bubble_count ?? '-' }}个 <el-tag :type="latestThermal.is_ng ? 'warning' : 'success'">{{ latestThermal.is_ng ? 'RISK' : 'OK' }}</el-tag></div></div>
            <div class="info-item"><div class="k">最新建议</div><div class="v"><template v-if="latestSug.id">#{{ latestSug.id }} · 置信度 {{ Math.round(latestSug.confidence * 100) }}% · 缺陷概率 {{ latestSug.defect_probability }}</template><template v-else>暂无</template></div></div>
            <div class="info-item"><div class="k">产线</div><div class="v">模式 {{ systemState.mode }} · {{ systemState.stopped ? '已停止' : '正常' }}</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card>
          <template #header><div class="panel-head"><span>本班判定分布</span><span class="sub">共 {{ thermals.length }} 台</span></div></template>
          <div style="display:flex; justify-content:center"><DonutChart :ok="okCount" :risk="riskCount" :ng="ngCount" /></div>
          <div class="dist-legend">
            <span>OK <b>{{ okCount }}</b> <span class="n">{{ pct(okCount) }}</span></span>
            <span>RISK <b>{{ riskCount }}</b> <span class="n">{{ pct(riskCount) }}</span></span>
            <span>NG <b>{{ ngCount }}</b> <span class="n">{{ pct(ngCount) }}</span></span>
          </div>
          <p class="card-note" style="text-align:center; margin: 10px 0 0">OK 为 A/B 且非 NG；RISK 为 C 且非 NG；NG 为热成像 NG 判定。</p>
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
