<template>
  <div class="view-stack">
    <el-card header="LLM 兜底工作台（本地知识检索 · 不直接控线）">
      <el-alert title="本工作台只返回证据与诊断报告，不写入 PLC。任何生产调整仍须走参数优化 → 审批 → 下发管控流程。" type="warning" :closable="false" />
      <el-form inline style="margin-top: 12px">
        <el-form-item><el-input v-model="query" placeholder="如：料温偏低 气泡" style="width: 320px" /></el-form-item>
        <el-form-item><el-button type="primary" @click="diag">检索证据并生成诊断</el-button></el-form-item>
      </el-form>
      <div v-if="diagnosis">
        <p>{{ diagnosis.report }}</p>
        <el-tag type="info">plc_control：{{ String(diagnosis.plc_control) }}（不控线）</el-tag>
        <el-table :data="diagnosis.evidence" style="margin-top: 10px">
          <el-table-column prop="title" label="证据标题" />
          <el-table-column prop="category" label="分类" />
          <el-table-column prop="source" label="来源" />
          <el-table-column prop="excerpt" label="摘要" />
        </el-table>
      </div>
      <el-divider />
      <el-form inline :model="sedForm">
        <el-form-item label="经验标题"><el-input v-model="sedForm.title" placeholder="经验标题" /></el-form-item>
        <el-form-item label="经验内容"><el-input v-model="sedForm.content" placeholder="经验内容" style="width: 320px" /></el-form-item>
        <el-form-item><el-button type="primary" @click="sed">专家标注沉淀入库</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-card header="知识表">
      <el-table :data="list">
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="category" label="分类" />
        <el-table-column prop="source" label="来源" />
        <el-table-column prop="content" label="内容" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const query = ref('')
const diagnosis = ref(null)
const sedForm = ref({ title: '', content: '' })
const list = ref([])

async function load() { list.value = await api('/api/knowledge') }
async function diag() {
  try { diagnosis.value = await api('/api/llm/diagnose', 'POST', { query: query.value }) }
  catch (e) { ElMessage.error(e.message) }
}
async function sed() {
  try {
    await api('/api/knowledge', 'POST', sedForm.value)
    ElMessage.success('已沉淀入库')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
onMounted(load)
</script>
