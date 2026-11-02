<template>
  <el-card header="审计日志（只读 · 追加式）">
    <p style="color: #909399">审计表无修改/删除接口，任何操作、审批、修正、启停、回退均留痕。</p>
    <el-table :data="list">
      <el-table-column prop="created_at" label="时间" />
      <el-table-column prop="actor" label="操作人" />
      <el-table-column prop="action" label="动作" />
      <el-table-column prop="entity" label="对象" />
      <el-table-column prop="detail" label="详情" />
    </el-table>
  </el-card>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const list = ref([])
onMounted(async () => {
  try { list.value = await api('/api/audit') }
  catch (e) { ElMessage.error(e.message) }
})
</script>
