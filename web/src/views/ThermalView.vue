<template>
  <div>
    <el-card header="热成像在线检测（五面覆盖 · A/B/C/D 分级）">
      <p style="color: #909399">输入气泡尺寸与数量，后端按规则分级；D 或 C 且数量≥10 为 NG，触发声光报警 + PLC NG信号 + 自动拦截。</p>
      <el-form inline :model="form">
        <el-form-item label="箱体条码"><el-input v-model="form.box_barcode" placeholder="如 BX-B-0101" /></el-form-item>
        <el-form-item label="最大气泡mm"><el-input-number v-model="form.max_bubble_mm" :step="0.1" /></el-form-item>
        <el-form-item label="气泡数量"><el-input-number v-model="form.bubble_count" /></el-form-item>
        <el-form-item><el-button type="primary" @click="submit">提交检测</el-button></el-form-item>
      </el-form>
      <el-alert v-if="result" :title="`等级 ${result.grade} · NG：${result.is_ng ? '是' : '否'} · ${result.action}`" type="info" :closable="false" />
    </el-card>
    <el-card header="检测结果" style="margin-top: 14px">
      <el-table :data="list">
        <el-table-column prop="box_barcode" label="箱体" />
        <el-table-column prop="grade" label="等级">
          <template #default="{ row }"><el-tag :type="row.grade === 'D' ? 'danger' : row.grade === 'C' ? 'warning' : 'success'">{{ row.grade }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="max_bubble_mm" label="最大气泡mm" />
        <el-table-column prop="bubble_count" label="数量" />
        <el-table-column label="NG"><template #default="{ row }">{{ row.is_ng ? '是' : '否' }}</template></el-table-column>
        <el-table-column prop="reviewed_by" label="复核人" />
        <el-table-column label="操作">
          <template #default="{ row }"><el-button size="small" @click="review(row)">热成像复核</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'

const form = ref({ box_barcode: '', max_bubble_mm: 3, bubble_count: 5 })
const list = ref([])
const result = ref(null)

async function load() { list.value = await api('/api/thermal-results') }
async function submit() {
  try {
    result.value = await api('/api/thermal-results', 'POST', form.value)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
async function review(row) {
  try {
    const { value } = await ElMessageBox.prompt('复核说明', '热成像复核', { inputValue: '' })
    await api(`/api/thermal-results/${row.id}/review`, 'POST', { note: value || '' })
    ElMessage.success('已复核')
    await load()
  } catch (e) { if (e.message) ElMessage.error(e.message) }
}
onMounted(load)
</script>
