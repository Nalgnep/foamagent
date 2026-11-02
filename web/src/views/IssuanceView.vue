<template>
  <div class="view-stack">
    <el-card header="下发管控（分级启用 · 8项校验 · 回退）">
      <p>当前模式：<b>{{ state.mode }}</b> · 系统停止：{{ state.stopped ? '是' : '否' }} · 安全基线：{{ JSON.stringify(state.safe_baseline) }}</p>
      <el-form inline>
        <el-form-item label="模式">
          <el-select v-model="mode" style="width: 160px">
            <el-option label="关闭" value="关闭" /><el-option label="人工确认" value="人工确认" /><el-option label="受控自动" value="受控自动" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button type="primary" @click="setMode">切换模式（管理员）</el-button></el-form-item>
        <el-form-item><el-button type="danger" @click="stopSys">急停/异常停止</el-button></el-form-item>
        <el-form-item><el-button type="primary" @click="resumeSys">人工恢复（管理员）</el-button></el-form-item>
      </el-form>
      <el-divider />
      <el-form inline :model="issueForm">
        <el-form-item label="建议ID"><el-input-number v-model="issueForm.suggestion_id" /></el-form-item>
        <el-form-item label="产品"><el-input v-model="issueForm.product" /></el-form-item>
        <el-form-item label="设备"><el-input v-model="issueForm.equipment" /></el-form-item>
        <el-form-item label="工况"><el-input v-model="issueForm.condition" /></el-form-item>
        <el-form-item><el-checkbox v-model="issueForm.approved">已审批</el-checkbox></el-form-item>
        <el-form-item><el-button type="primary" @click="issue">执行8项校验并下发</el-button></el-form-item>
      </el-form>
      <div v-if="issueResult">
        <el-alert :title="issueResult.ok ? `下发成功：${issueResult.plc_receipt}` : '下发被阻断'" :type="issueResult.ok ? 'success' : 'warning'" :closable="false" />
        <el-table :data="issueResult.checks || []">
          <el-table-column prop="name" label="校验项" />
          <el-table-column label="通过"><template #default="{ row }"><el-tag :type="row.passed ? 'success' : 'danger'">{{ row.passed ? '通过' : '未通过' }}</el-tag></template></el-table-column>
          <el-table-column prop="detail" label="详情" />
        </el-table>
      </div>
    </el-card>
    <el-card header="下发表">
      <el-table :data="list">
        <el-table-column prop="id" label="下发ID" />
        <el-table-column prop="suggestion_id" label="建议ID" />
        <el-table-column prop="mode" label="模式" />
        <el-table-column prop="status" label="状态" />
        <el-table-column prop="plc_receipt" label="PLC回执" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button v-if="row.status === 'issued'" size="small" @click="rollback(row.id)">一键回退</el-button>
            <span v-else>-</span>
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

const state = ref({ mode: '', stopped: false, safe_baseline: {} })
const list = ref([])
const mode = ref('人工确认')
const issueForm = ref({ suggestion_id: null, product: 'BCD-520W', equipment: 'B-LINE-FOAM-01', condition: 'normal', approved: true })
const issueResult = ref(null)

async function load() {
  state.value = await api('/api/system/state')
  mode.value = state.value.mode
  list.value = await api('/api/issuances')
}
async function setMode() { try { await api('/api/system/mode', 'POST', { mode: mode.value }); await load() } catch (e) { ElMessage.error(e.message) } }
async function stopSys() { try { await api('/api/system/stop', 'POST', { reason: '前端模拟急停/报警' }); await load() } catch (e) { ElMessage.error(e.message) } }
async function resumeSys() { try { await api('/api/system/resume', 'POST', {}); await load() } catch (e) { ElMessage.error(e.message) } }
async function issue() {
  try {
    issueResult.value = await api('/api/issuance', 'POST', issueForm.value)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
async function rollback(id) { try { await api(`/api/issuance/${id}/rollback`, 'POST', {}); await load() } catch (e) { ElMessage.error(e.message) } }
onMounted(load)
</script>
