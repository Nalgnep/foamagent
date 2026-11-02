<template>
  <div class="view-stack">
    <el-card header="灯塔运营">
      <p>权重：质量 {{ data.weights?.quality }} · 原料 {{ data.weights?.material }} · 能耗 {{ data.weights?.energy }}</p>
      <el-form inline>
        <el-form-item label="质量"><el-input-number v-model="weights.quality" :step="0.1" /></el-form-item>
        <el-form-item label="原料"><el-input-number v-model="weights.material" :step="0.1" /></el-form-item>
        <el-form-item label="能耗"><el-input-number v-model="weights.energy" :step="0.1" /></el-form-item>
        <el-form-item><el-button type="primary" @click="setWeights">调整权重（管理员）</el-button></el-form-item>
      </el-form>
      <p>一次合格率：{{ (data.quality?.first_pass_rate * 100).toFixed(1) }}% · 换产记录：{{ data.changeover?.records }} 条 · 爬坡缺陷率：{{ (data.changeover?.ramp_defect_rate * 100).toFixed(1) }}% · 知识条目：{{ data.knowledge_items }}</p>
      <p>放行门：{{ JSON.stringify(data.release_gates) }}</p>
      <el-divider />
      <el-form inline :model="coForm">
        <el-form-item label="原产品"><el-input v-model="coForm.from_product" placeholder="原产品" /></el-form-item>
        <el-form-item label="新产品"><el-input v-model="coForm.to_product" placeholder="新产品" /></el-form-item>
        <el-form-item label="爬坡台数"><el-input-number v-model="coForm.ramp_boxes" /></el-form-item>
        <el-form-item label="爬坡缺陷数"><el-input-number v-model="coForm.ramp_defects" /></el-form-item>
        <el-form-item><el-button type="primary" @click="addCo">记录换产爬坡</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-card header="9 包多线复制包">
      <el-table :data="data.replication">
        <el-table-column prop="name" label="包" />
        <el-table-column prop="status" label="状态">
          <template #default="{ row }"><el-tag :type="row.status === '已就绪' ? 'success' : 'info'">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="note" label="备注" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const data = ref({ weights: {}, quality: {}, changeover: {}, replication: [] })
const weights = ref({ quality: 0.5, material: 0.3, energy: 0.2 })
const coForm = ref({ from_product: '', to_product: '', ramp_boxes: 0, ramp_defects: 0 })

async function load() {
  data.value = await api('/api/lighthouse')
  weights.value = { ...data.value.weights }
}
async function setWeights() { try { await api('/api/lighthouse/weights', 'POST', weights.value); await load() } catch (e) { ElMessage.error(e.message) } }
async function addCo() { try { await api('/api/changeovers', 'POST', coForm.value); await load() } catch (e) { ElMessage.error(e.message) } }
onMounted(load)
</script>
