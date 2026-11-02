<template>
  <div>
    <el-card header="闭环追踪">
      <p style="color: #909399">在线感知 → 质量判定 → 工艺分析 → 参数建议/受控下发 → 效果验证 → 知识沉淀。输入一个箱体条码，查看它走完闭环的每一步；没有走到的环节会明确标为待办，不会用演示数据冒充已完成。</p>
      <el-form inline>
        <el-form-item><el-input v-model="barcode" placeholder="箱体条码，如 BX-B-0001" style="width: 220px" /></el-form-item>
        <el-form-item><el-button type="primary" @click="lookup">查本箱时间线</el-button></el-form-item>
      </el-form>
      <div v-if="timeline">
        <p>箱体 {{ timeline.box.barcode }} · 夹具 {{ timeline.box.fixture_no }} · 产品 {{ timeline.box.product }} · 状态 {{ timeline.box.status }}</p>
        <el-alert :title="`下一步：${timeline.next_step}`" type="info" :closable="false" style="margin-bottom: 12px" />
        <el-steps :active="doneCount" finish-status="success" style="margin-bottom: 16px">
          <el-step v-for="s in timeline.stages" :key="s.stage" :title="s.stage" :description="s.done ? '已完成' : '待办'" />
        </el-steps>
        <p v-for="s in timeline.stages" :key="s.stage" v-show="s.note" style="color: #909399; font-size: 13px">{{ s.stage }}：{{ s.note }}</p>
        <el-table :data="timeline.events">
          <el-table-column prop="stage" label="环节" />
          <el-table-column prop="title" label="事件" />
          <el-table-column prop="detail" label="详情" />
          <el-table-column prop="created_at" label="时间" />
        </el-table>
      </div>
    </el-card>

    <el-card header="双轨 KPI：协议基线 vs 灯塔拔高目标" style="margin-top: 14px">
      <p style="color: #909399">生产模型：{{ dual.production_model || '-' }} · {{ dual.note }}</p>
      <el-table :data="dual.rows">
        <el-table-column prop="metric" label="指标" />
        <el-table-column prop="protocol" label="协议基线" />
        <el-table-column prop="lighthouse" label="灯塔目标" />
        <el-table-column label="当前值"><template #default="{ row }">{{ row.current === null ? '未验证' : row.current }}</template></el-table-column>
        <el-table-column label="状态"><template #default="{ row }"><el-tag :type="tagTypeForStatus(row.status)">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="note" label="口径说明" />
      </el-table>
    </el-card>

    <el-card header="下发效果验证" style="margin-top: 14px">
      <p style="color: #909399">下发前等级为该箱体下发前最后一次热成像，下发后等级为下发后最后一次；没有下发后检测时明确标“待验证”，不补算。</p>
      <el-table :data="effects">
        <el-table-column prop="issuance_id" label="下发ID" />
        <el-table-column prop="box_barcode" label="箱体" />
        <el-table-column prop="status" label="状态" />
        <el-table-column prop="pre_grade" label="下发前" />
        <el-table-column prop="post_grade" label="下发后" />
        <el-table-column label="结论"><template #default="{ row }"><el-tag :type="tagTypeForStatus(row.result)">{{ row.result }}</el-tag></template></el-table-column>
        <el-table-column label="操作"><template #default="{ row }"><el-button size="small" @click="verify(row.issuance_id)">记录一次验证</el-button></template></el-table-column>
      </el-table>
      <pre v-if="verifyOut" style="white-space: pre-wrap">{{ verifyOut }}</pre>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, tagTypeForStatus } from '../api.js'

const barcode = ref('BX-B-0001')
const timeline = ref(null)
const dual = ref({ rows: [] })
const effects = ref([])
const verifyOut = ref('')

const doneCount = computed(() => timeline.value ? timeline.value.stages.filter((s) => s.done).length : 0)

async function lookup() {
  if (!barcode.value.trim()) return
  try { timeline.value = await api(`/api/boxes/${encodeURIComponent(barcode.value.trim())}/timeline`) }
  catch (e) { ElMessage.error(e.message) }
}
async function loadStatic() {
  try {
    dual.value = await api('/api/kpi/dual-track')
    effects.value = await api('/api/issuances/effects')
  } catch (e) { ElMessage.error(e.message) }
}
async function verify(id) {
  try {
    const r = await api(`/api/issuances/${id}/verify`, 'POST', {})
    verifyOut.value = JSON.stringify(r, null, 2)
    effects.value = await api('/api/issuances/effects')
  } catch (e) { ElMessage.error(e.message) }
}
onMounted(async () => { await loadStatic(); await lookup() })
</script>
