<template>
  <el-container style="height: 100vh">
    <el-header class="topbar">
      <div class="brand">
        <span class="logo-mark">H</span>
        <span class="logo">Hisense</span>
        <span class="sys">发泡工艺智能系统</span>
        <span class="page">{{ currentLabel }}</span>
      </div>
      <div class="top-links">
        <el-button link @click="go('thermal', '复核判定')">热成像系统</el-button>
        <el-button link @click="go('llm', '根因分析报告')">智能体平台</el-button>
        <el-badge :value="unreviewedNg || undefined" type="danger">
          <span title="未复核 NG">🔔</span>
        </el-badge>
        <span>演示用户</span>
        <el-select v-model="userState.username" style="width: 220px" @change="reloadKey++">
          <el-option
            v-for="u in userState.users"
            :key="u.username"
            :label="`${u.display_name}（${u.username} · ${u.role}）`"
            :value="u.username"
          />
        </el-select>
        <span class="who">{{ currentUserName }}</span>
      </div>
    </el-header>
    <el-container>
      <el-aside width="220px" class="sidebar">
        <el-menu :default-active="current" @select="onMenuSelect">
          <el-menu-item index="dashboard">仪表盘</el-menu-item>
          <el-menu-item index="trace">我的待办</el-menu-item>
          <el-sub-menu index="model-check">
            <template #title>模型检测</template>
            <el-menu-item index="thermal">复核判定</el-menu-item>
            <el-menu-item index="audit">记录查询</el-menu-item>
            <el-menu-item index="closedloop">质量分析</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="trace-mgmt">
            <template #title>追溯管理</template>
            <el-menu-item index="trace">箱体追溯</el-menu-item>
            <el-menu-item index="trace">异常处理</el-menu-item>
            <el-menu-item index="lighthouse">批次分析</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="model-lib">
            <template #title>模型库</template>
            <el-menu-item index="model">边缘模型</el-menu-item>
            <el-menu-item index="validation">机理模型</el-menu-item>
            <el-menu-item index="validation">模型体检</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="agent">
            <template #title>智能体</template>
            <el-menu-item index="llm">根因分析报告</el-menu-item>
            <el-menu-item index="optimize">参数建议报告</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="system">
            <template #title>系统管控</template>
            <el-menu-item index="audit">全程留痕</el-menu-item>
          </el-sub-menu>
        </el-menu>
        <div class="sidebar-footer">
          <div><b style="color: var(--ink)">成都 B 线 · 箱体发泡</b></div>
          <div>演示数据（模拟）· PLC 模拟回执</div>
          <div>不可直接用于真实产线控制</div>
        </div>
      </el-aside>
      <el-main>
        <component :is="views[current]" :key="current + '-' + reloadKey" @navigate="go" />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, loadUsers, userState } from './api.js'
import DashboardView from './views/DashboardView.vue'
import ClosedLoopView from './views/ClosedLoopView.vue'
import ThermalView from './views/ThermalView.vue'
import TraceView from './views/TraceView.vue'
import OptimizeView from './views/OptimizeView.vue'
import IssuanceView from './views/IssuanceView.vue'
import LlmView from './views/LlmView.vue'
import ModelView from './views/ModelView.vue'
import ValidationView from './views/ValidationView.vue'
import LighthouseView from './views/LighthouseView.vue'
import AuditView from './views/AuditView.vue'

const views = {
  dashboard: DashboardView,
  closedloop: ClosedLoopView,
  thermal: ThermalView,
  trace: TraceView,
  optimize: OptimizeView,
  issuance: IssuanceView,
  llm: LlmView,
  model: ModelView,
  validation: ValidationView,
  lighthouse: LighthouseView,
  audit: AuditView
}
const labels = {
  dashboard: '仪表盘', closedloop: '质量分析', thermal: '复核判定',
  trace: '箱体追溯', optimize: '参数建议报告', issuance: '下发管控',
  llm: '根因分析报告', model: '边缘模型', validation: '机理模型',
  lighthouse: '批次分析', audit: '全程留痕'
}
const current = ref('dashboard')
const currentLabel = computed(() => labels[current.value] || current.value)
const reloadKey = ref(0)
const unreviewedNg = ref(0)
const currentUserName = computed(() => {
  const u = userState.users.find((x) => x.username === userState.username)
  return u ? u.display_name : ''
})

function go(view, label) {
  if (views[view]) {
    current.value = view
    if (label) labels[view] = label
  }
}
function onMenuSelect(index) {
  if (views[index]) current.value = index
}

onMounted(async () => {
  try {
    await loadUsers()
    const thermals = await api('/api/thermal-results')
    unreviewedNg.value = thermals.filter((t) => t.is_ng && !t.reviewed_by).length
  } catch (e) {
    // Bell badge is best-effort; the views surface real API errors themselves.
  }
})
</script>

<style>
.el-main { background: var(--bg); }
</style>
