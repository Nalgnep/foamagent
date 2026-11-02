<template>
  <div>
    <el-card header="参数优化">
      <p style="color: #909399">输入工艺参数，后端计算缺陷概率、置信度、可行域；不可行或置信度&lt;0.70 或分布外时自动转 LLM 工作台，不自动下发。优化走模型适配器，机理孪生返回约束校验结果。</p>
      <el-form inline :model="form" label-width="80px">
        <el-form-item label="料比"><el-input-number v-model="form.material_ratio" :step="0.01" /></el-form-item>
        <el-form-item label="料温℃"><el-input-number v-model="form.material_temp" /></el-form-item>
        <el-form-item label="模芯温度℃"><el-input-number v-model="form.core_temp" /></el-form-item>
        <el-form-item label="固化时间s"><el-input-number v-model="form.curing_time" /></el-form-item>
        <el-form-item label="夹具温度℃"><el-input-number v-model="form.fixture_temp" /></el-form-item>
        <el-form-item label="箱体条码"><el-input v-model="form.box_barcode" placeholder="箱体条码" /></el-form-item>
        <el-form-item><el-button type="primary" @click="run">运行优化</el-button></el-form-item>
      </el-form>
      <div v-if="result">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="建议ID">{{ result.suggestion_id }}</el-descriptions-item>
          <el-descriptions-item label="模型适配器">{{ result.model_adapter }}</el-descriptions-item>
          <el-descriptions-item label="缺陷概率">{{ result.defect_probability }}</el-descriptions-item>
          <el-descriptions-item label="置信度">{{ result.confidence }}</el-descriptions-item>
          <el-descriptions-item label="可行域">{{ result.feasible ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="转LLM">{{ result.routed_to_llm ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="分布外">{{ result.out_of_distribution ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="目标分">{{ result.objective_score }}</el-descriptions-item>
          <el-descriptions-item label="建议参数">{{ JSON.stringify(result.suggested) }}</el-descriptions-item>
          <el-descriptions-item label="机理孪生">
            可行：{{ result.mechanism_twin?.feasible ? '是' : '否' }}；违反约束：{{ (result.mechanism_twin?.constraints_violated || []).join('；') || '无' }}
          </el-descriptions-item>
          <el-descriptions-item label="模型说明">{{ result.model_note }}</el-descriptions-item>
          <el-descriptions-item label="原因">{{ (result.reasons || []).join('；') }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>
    <el-card header="建议表" style="margin-top: 14px">
      <el-table :data="list">
        <el-table-column prop="id" label="建议ID" />
        <el-table-column prop="box_barcode" label="箱体" />
        <el-table-column prop="defect_probability" label="缺陷概率" />
        <el-table-column prop="confidence" label="置信度" />
        <el-table-column label="可行"><template #default="{ row }">{{ row.feasible ? '是' : '否' }}</template></el-table-column>
        <el-table-column label="转LLM"><template #default="{ row }">{{ row.routed_to_llm ? '是' : '否' }}</template></el-table-column>
        <el-table-column prop="status" label="状态" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const form = ref({ material_ratio: 1.08, material_temp: 22, core_temp: 45, curing_time: 360, fixture_temp: 40, box_barcode: '' })
const list = ref([])
const result = ref(null)

async function load() { list.value = await api('/api/suggestions') }
async function run() {
  try {
    result.value = await api('/api/optimize', 'POST', form.value)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
onMounted(load)
</script>
