<template>
  <div>
    <el-card header="箱体条码追溯（多条件关联 · 异常不硬绑）">
      <p style="color: #909399">重复条码、缺失、夹具冲突、乱序都会进入异常队列，状态为“待确认/关联异常”，须管理员人工修正；系统不会凭时间相近硬绑。</p>
      <el-form inline :model="form">
        <el-form-item label="箱体条码"><el-input v-model="form.barcode" placeholder="箱体条码" /></el-form-item>
        <el-form-item label="夹具号"><el-input v-model="form.fixture_no" placeholder="夹具号" /></el-form-item>
        <el-form-item><el-checkbox v-model="form.out_of_order">时间戳乱序（模拟）</el-checkbox></el-form-item>
        <el-form-item><el-button type="primary" @click="bind">绑定</el-button></el-form-item>
      </el-form>
      <el-alert v-if="result" :title="result.bound ? `已绑定：${result.barcode}` : `未硬绑：${result.detail}（已进入异常队列）`" :type="result.bound ? 'success' : 'warning'" :closable="false" />
    </el-card>
    <el-card header="异常队列" style="margin-top: 14px">
      <el-table :data="list">
        <el-table-column prop="barcode" label="条码" />
        <el-table-column prop="fixture_no" label="夹具" />
        <el-table-column prop="kind" label="类型" />
        <el-table-column prop="status" label="状态">
          <template #default="{ row }"><el-tag :type="row.status === '待确认/关联异常' ? 'warning' : 'success'">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button v-if="row.status === '待确认/关联异常'" size="small" @click="resolve(row.id)">人工修正</el-button>
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

const form = ref({ barcode: '', fixture_no: '', out_of_order: false })
const list = ref([])
const result = ref(null)

async function load() { list.value = await api('/api/trace/exceptions') }
async function bind() {
  try {
    result.value = await api('/api/trace/bind', 'POST', form.value)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
async function resolve(id) {
  try {
    await api(`/api/trace/exceptions/${id}/resolve`, 'POST', { note: '前端人工修正演示' })
    ElMessage.success('已人工修正')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
onMounted(load)
</script>
