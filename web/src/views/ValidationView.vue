<template>
  <div class="view-stack">
    <el-card header="模型验证：适配器与独立验证">
      <p class="card-note">优化接口已改为走模型适配器：当前为本地规则；训练模型槽位未接入，选中会被后端拒绝，直到提供模型文件、特征清单并通过独立验证。</p>
      <p>当前适配器：<el-tag type="info">{{ adapters.active }}</el-tag></p>
      <el-table :data="adapters.adapters">
        <el-table-column prop="name" label="适配器" />
        <el-table-column prop="kind" label="类型" />
        <el-table-column label="已接入"><template #default="{ row }">{{ row.loaded ? '是' : '否' }}</template></el-table-column>
        <el-table-column label="当前"><template #default="{ row }">{{ row.active ? '是' : '否' }}</template></el-table-column>
        <el-table-column prop="description" label="说明" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button v-if="row.loaded && !row.active" size="small" @click="selectAd(row.name)">设为当前</el-button>
            <el-button v-else-if="!row.loaded" size="small" @click="selectAd(row.name)">尝试切换（后端会拒绝）</el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card header="机理孪生（约束框架，未验证）">
      <div class="info-grid">
        <div class="info-item"><div class="k">状态</div><div class="v">{{ twin.status }}</div></div>
        <div class="info-item"><div class="k">需验证组数</div><div class="v">{{ twin.required_groups }}</div></div>
        <div class="info-item"><div class="k">趋势一致性要求</div><div class="v">≥{{ (twin.trend_consistency_required * 100).toFixed(0) }}%</div></div>
        <div class="info-item"><div class="k">归一化误差上限</div><div class="v">{{ twin.normalized_error_max }}</div></div>
        <div class="info-item"><div class="k">已验证组数</div><div class="v">{{ twin.validated_groups }}</div></div>
        <div class="info-item"><div class="k">趋势一致性</div><div class="v">{{ twin.trend_consistency === null ? '未验证' : twin.trend_consistency }}</div></div>
      </div>
      <p class="card-note">{{ twin.note }}</p>
    </el-card>

    <el-card header="跑一次独立验证">
      <p class="card-note">粘贴冻结验证集 JSON（每条含 5 个工艺参数 + is_ng，is_high_risk / is_severe 可选）。预测 NG 的口径固定为：缺陷概率 ≥0.50 或超出可行域。结论只对这批样本负责。</p>
      <el-form>
        <el-form-item><el-input v-model="datasetName" placeholder="数据集名称，如 2026-11-冻结验证集A" style="width: 320px" /></el-form-item>
        <el-form-item><el-input v-model="datasetJson" type="textarea" :rows="8" /></el-form-item>
        <el-form-item><el-button type="primary" @click="runVal">运行验证并留存</el-button></el-form-item>
      </el-form>
      <pre v-if="valOut" class="result-pre">{{ valOut }}</pre>
    </el-card>

    <el-card header="验证记录">
      <el-table :data="runs">
        <el-table-column prop="id" label="ID" />
        <el-table-column prop="adapter" label="适配器" />
        <el-table-column prop="dataset_name" label="数据集" />
        <el-table-column prop="sample_count" label="样本数" />
        <el-table-column prop="severe_miss" label="严重漏检" />
        <el-table-column prop="high_risk_recall" label="高风险召回" />
        <el-table-column prop="false_alarm_rate" label="误报率" />
        <el-table-column label="结论"><template #default="{ row }"><el-tag :type="tagTypeForStatus(row.verdict)">{{ row.verdict }}</el-tag></template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, tagTypeForStatus } from '../api.js'

const adapters = ref({ active: '', adapters: [] })
const twin = ref({})
const runs = ref([])
const datasetName = ref('')
const datasetJson = ref(JSON.stringify([
  { material_ratio: 1.08, material_temp: 22, core_temp: 45, curing_time: 360, fixture_temp: 40, is_ng: 0, is_high_risk: 0, is_severe: 0 },
  { material_ratio: 1.30, material_temp: 35, core_temp: 70, curing_time: 60, fixture_temp: 60, is_ng: 1, is_high_risk: 1, is_severe: 1 }
], null, 2))
const valOut = ref('')

async function load() {
  adapters.value = await api('/api/models/adapters')
  twin.value = await api('/api/models/mechanism-twin')
  runs.value = await api('/api/validation/runs')
}
async function selectAd(name) {
  try {
    await api('/api/models/adapters/select', 'POST', { adapter: name })
    ElMessage.success('已切换')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
async function runVal() {
  try {
    const samples = JSON.parse(datasetJson.value)
    const r = await api('/api/validation/evaluate', 'POST', { dataset_name: datasetName.value, samples })
    valOut.value = JSON.stringify(r, null, 2)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
onMounted(load)
</script>
