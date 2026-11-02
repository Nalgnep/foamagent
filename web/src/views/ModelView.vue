<template>
  <div class="view-stack">
    <el-card header="模型全生命周期">
      <p>漂移代理指标：近期NG率 {{ drift.recent_ng_rate }}，漂移分数 {{ drift.drift_score }}，预警：{{ drift.warning ? '是' : '否' }}（{{ drift.note }}）</p>
      <el-table :data="list">
        <el-table-column prop="name" label="模型" />
        <el-table-column prop="version" label="版本" />
        <el-table-column prop="status" label="状态">
          <template #default="{ row }"><el-tag :type="row.status === 'production' ? 'success' : row.status === 'shadow' ? 'warning' : 'info'">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="recall" label="召回" />
        <el-table-column prop="false_alarm" label="误报" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button v-if="row.status === 'shadow'" size="small" @click="promote(row.id)">影子晋升生产</el-button>
            <el-button v-else size="small" @click="rollbackM(row.id)">回退到此版本</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const list = ref([])
const drift = ref({})

async function load() {
  list.value = await api('/api/models')
  drift.value = await api('/api/models/drift')
}
async function promote(id) { try { await api(`/api/models/${id}/promote`, 'POST', {}); await load() } catch (e) { ElMessage.error(e.message) } }
async function rollbackM(id) { try { await api(`/api/models/${id}/rollback`, 'POST', {}); await load() } catch (e) { ElMessage.error(e.message) } }
onMounted(load)
</script>
