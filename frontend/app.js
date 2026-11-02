const tabs = ["驾驶舱", "闭环追踪", "热成像", "追溯", "参数优化", "下发管控", "LLM工作台", "模型管理", "模型验证", "灯塔运营", "审计"];
let current = "驾驶舱";
const main = document.getElementById("main");
const userSel = document.getElementById("user");
function headers() { return { "Content-Type": "application/json", "X-User": userSel.value }; }
async function api(path, method = "GET", body = null) {
  const r = await fetch(path, { method, headers: headers(), body: body ? JSON.stringify(body) : null });
  const t = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(t.detail || JSON.stringify(t));
  return t;
}
function esc(s) { return String(s ?? "").replace(/</g, "&lt;"); }
function badge(text, kind) { return `<span class="badge ${kind}">${esc(text)}</span>`; }
function statusBadge(s) {
  if (s && s.includes("达标")) return badge(s, "ok");
  if (s && s.includes("未验证")) return badge(s, "neutral");
  if (s && s.includes("演示口径")) return badge(s, "info");
  if (s && s.includes("未达") || s && s.includes("恶化")) return badge(s, "bad");
  if (s && s.includes("改善")) return badge(s, "ok");
  return badge(s || "-", "neutral");
}
function rows(list, cols) {
  if (!list.length) return "<p class='note'>暂无数据</p>";
  return "<table><tr>" + cols.map(c => `<th>${c[0]}</th>`).join("") + "</tr>" +
    list.map(r => "<tr>" + cols.map(c => {
      const v = typeof c[1] === "function" ? c[1](r) : r[c[1]];
      return `<td>${String(v).startsWith("<span class=\"badge") ? v : esc(v)}</td>`;
    }).join("") + "</tr>").join("") + "</table>";
}
async function render() {
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("active", b.textContent === current));
  try { await views[current](); } catch (e) { main.innerHTML = `<div class="card warn">请求失败：${esc(e.message)}<br>请先确认后端已启动且已选择演示用户。</div>`; }
}
const views = {
  async 驾驶舱() {
    const d = await api("/api/dashboard"), s = await api("/api/system/state");
    main.innerHTML = `<div class="card"><div class="card-head"><h2>驾驶舱</h2>${s.stopped ? badge("已停止（异常）", "bad") : badge("运行正常", "ok")}</div><div class="grid">
      <div class="kpi"><span>箱体数</span><b>${d.kpis.boxes}</b></div><div class="kpi"><span>热成像检测</span><b>${d.kpis.thermal_checked}</b></div>
      <div class="kpi"><span>NG 数</span><b>${d.kpis.ng_count}</b></div><div class="kpi"><span>一次合格率</span><b>${(d.kpis.first_pass_rate * 100).toFixed(1)}%</b></div>
      <div class="kpi"><span>追溯异常待确认</span><b>${d.kpis.trace_exceptions_open}</b></div><div class="kpi"><span>已下发</span><b>${d.kpis.issued_count}</b></div>
      <div class="kpi"><span>知识条目</span><b>${d.kpis.knowledge_items}</b></div><div class="kpi"><span>当前模式</span><b>${d.kpis.mode}</b></div></div>
      <p>生产模型：${d.kpis.production_model || "-"} · 演示数据（模拟），PLC 为模拟回执</p>
      <div class="steps">${d.closed_loop.map(x => `<div class="step done"><span class="dot"></span>${x}</div>`).join("")}</div>
      <p class="note">协议基线：${JSON.stringify(d.protocol_baseline)} · 闭环时间线、协议 vs 灯塔双轨 KPI、下发效果验证见“闭环追踪”页签；模型适配器与独立验证见“模型验证”页签。</p></div>`;
  },
  async 闭环追踪() {
    const kpi = await api("/api/kpi/dual-track"), eff = await api("/api/issuances/effects");
    main.innerHTML = `<div class="card"><h2>闭环追踪：在线感知 → 质量判定 → 工艺分析 → 参数建议/受控下发 → 效果验证 → 知识沉淀</h2>
      <p class="note">输入一个箱体条码，查看它走完闭环的每一步；没有走到的环节会明确标为待办，不会用演示数据冒充已完成。</p>
      <input id="tb" placeholder="箱体条码，如 BX-B-0001" value="BX-B-0001" style="width:220px">
      <button class="primary" onclick="lookupTimeline()">查本箱时间线</button><div id="timeline"></div></div>
      <div class="card"><h3>双轨 KPI：协议基线 vs 灯塔拔高目标</h3>
      <p class="note">生产模型：${kpi.production_model || "-"} · ${kpi.note}</p>
      ${rows(kpi.rows, [["指标", "metric"], ["协议基线", "protocol"], ["灯塔目标", "lighthouse"], ["当前值", r => r.current === null ? "未验证" : r.current], ["状态", r => statusBadge(r.status)], ["口径说明", "note"]])}</div>
      <div class="card"><h3>下发效果验证</h3><p class="note">下发前等级为该箱体下发前最后一次热成像，下发后等级为下发后最后一次；没有下发后检测时明确标“待验证”，不补算。</p>
      ${rows(eff, [["下发ID", "issuance_id"], ["箱体", "box_barcode"], ["状态", "status"], ["下发前", "pre_grade"], ["下发后", "post_grade"], ["结论", r => statusBadge(r.result)], ["操作", r => `<button onclick="verifyIss(${r.issuance_id})">记录一次验证</button>`]])}<pre id="vout"></pre></div>`;
    window.lookupTimeline = async () => {
      const b = document.getElementById("tb").value.trim();
      if (!b) return;
      try {
        const t = await api(`/api/boxes/${encodeURIComponent(b)}/timeline`);
        document.getElementById("timeline").innerHTML = `<hr><p>箱体 ${t.box.barcode} · 夹具 ${t.box.fixture_no} · 产品 ${t.box.product} · 状态 ${t.box.status}</p>
          <p>下一步：<b>${t.next_step}</b></p>
          <div class="steps">${t.stages.map(s => `<div class="step ${s.done ? "done" : ""}"><span class="dot"></span>${s.stage}<br><span class="note">${s.done ? "已完成" : "待办"}</span></div>`).join("")}</div>
          ${rows(t.events, [["环节", "stage"], ["事件", "title"], ["详情", "detail"], ["时间", "created_at"]])}`;
      } catch (e) { document.getElementById("timeline").innerHTML = `<p class="warn">${esc(e.message)}</p>`; }
    };
    window.verifyIss = async (id) => { const r = await api(`/api/issuances/${id}/verify`, "POST", {}); document.getElementById("vout").textContent = JSON.stringify(r, null, 2); };
    window.lookupTimeline();
  },
  async 热成像() {
    const list = await api("/api/thermal-results");
    main.innerHTML = `<div class="card"><h2>热成像在线检测（五面覆盖 · A/B/C/D 分级）</h2>
      <p class="note">输入气泡尺寸与数量，后端按规则分级；D 或 C 且数量≥10 为 NG，触发声光报警 + PLC NG信号 + 自动拦截。</p>
      <input id="b" placeholder="箱体条码，如 BX-B-0101"> <input id="mm" type="number" step="0.1" value="3" placeholder="最大气泡mm">
      <input id="n" type="number" value="5" placeholder="气泡数量">
      <button class="primary" onclick="submitThermal()">提交检测</button><pre id="out"></pre></div>
      <div class="card">${rows(list, [["箱体", "box_barcode"], ["等级", "grade"], ["最大气泡mm", "max_bubble_mm"], ["数量", "bubble_count"], ["NG", r => r.is_ng ? "是" : "否"], ["复核人", "reviewed_by"]])}</div>`;
    window.submitThermal = async () => {
      const r = await api("/api/thermal-results", "POST", { box_barcode: document.getElementById("b").value, max_bubble_mm: parseFloat(document.getElementById("mm").value), bubble_count: parseInt(document.getElementById("n").value) });
      document.getElementById("out").textContent = JSON.stringify(r, null, 2); render();
    };
  },
  async 追溯() {
    const list = await api("/api/trace/exceptions");
    main.innerHTML = `<div class="card"><h2>箱体条码追溯（多条件关联 · 异常不硬绑）</h2>
      <input id="b" placeholder="箱体条码"> <input id="f" placeholder="夹具号">
      <label><input type="checkbox" id="ooo"> 时间戳乱序（模拟）</label>
      <button class="primary" onclick="bind()">绑定</button><pre id="out"></pre>
      <p class="note">重复条码、缺失、夹具冲突、乱序都会进入异常队列，状态为“待确认/关联异常”，须管理员人工修正。</p></div>
      <div class="card"><h3>异常队列</h3>${rows(list, [["条码", "barcode"], ["夹具", "fixture_no"], ["类型", "kind"], ["状态", "status"], ["详情", "detail"], ["操作", r => r.status === "待确认/关联异常" ? `<button onclick="resolveExc(${r.id})">人工修正</button>` : "-"]])}</div>`;
    window.bind = async () => {
      const r = await api("/api/trace/bind", "POST", { barcode: document.getElementById("b").value, fixture_no: document.getElementById("f").value, out_of_order: document.getElementById("ooo").checked });
      document.getElementById("out").textContent = JSON.stringify(r, null, 2); render();
    };
    window.resolveExc = async (id) => { await api(`/api/trace/exceptions/${id}/resolve`, "POST", { note: "前端人工修正演示" }); render(); };
  },
  async 参数优化() {
    const list = await api("/api/suggestions");
    main.innerHTML = `<div class="card"><h2>参数优化（本地确定性规则，非训练模型）</h2>
      <p class="note">输入工艺参数，后端计算缺陷概率、置信度、可行域；不可行或置信度&lt;0.70 或分布外时自动转 LLM 工作台，不自动下发。</p>
      <input id="ratio" type="number" step="0.01" value="1.08" placeholder="料比"> <input id="mt" type="number" value="22" placeholder="料温℃">
      <input id="ct" type="number" value="45" placeholder="模芯温度℃"> <input id="cur" type="number" value="360" placeholder="固化时间s">
      <input id="ft" type="number" value="40" placeholder="夹具温度℃"> <input id="box" placeholder="箱体条码">
      <button class="primary" onclick="opt()">运行优化</button><pre id="out"></pre></div>
      <div class="card">${rows(list, [["建议ID", "id"], ["箱体", "box_barcode"], ["缺陷概率", "defect_probability"], ["置信度", "confidence"], ["可行", r => r.feasible ? "是" : "否"], ["转LLM", r => r.routed_to_llm ? "是" : "否"], ["状态", "status"]])}</div>`;
    window.opt = async () => {
      const r = await api("/api/optimize", "POST", { material_ratio: parseFloat(document.getElementById("ratio").value), material_temp: parseFloat(document.getElementById("mt").value), core_temp: parseFloat(document.getElementById("ct").value), curing_time: parseFloat(document.getElementById("cur").value), fixture_temp: parseFloat(document.getElementById("ft").value), box_barcode: document.getElementById("box").value });
      document.getElementById("out").textContent = JSON.stringify(r, null, 2); render();
    };
  },
  async 下发管控() {
    const s = await api("/api/system/state"), list = await api("/api/issuances"), sugs = await api("/api/suggestions");
    main.innerHTML = `<div class="card"><h2>下发管控（分级启用 · 8项校验 · 回退）</h2>
      <p>当前模式：<b>${s.mode}</b> · 系统停止：${s.stopped ? "是" : "否"} · 安全基线：${JSON.stringify(s.safe_baseline)}</p>
      <select id="mode"><option>关闭</option><option>人工确认</option><option>受控自动</option></select>
      <button class="primary" onclick="setMode()">切换模式（管理员）</button>
      <button class="danger" onclick="stopSys()">急停/异常停止</button> <button class="primary" onclick="resumeSys()">人工恢复（管理员）</button>
      <hr><input id="sid" type="number" placeholder="建议ID（见参数优化页）">
      <button class="primary" onclick="issue()">执行8项校验并下发</button><pre id="out"></pre></div>
      <div class="card">${rows(list, [["下发ID", "id"], ["建议ID", "suggestion_id"], ["模式", "mode"], ["状态", "status"], ["PLC回执", "plc_receipt"], ["操作", r => r.status === "issued" ? `<button onclick="rollback(${r.id})">一键回退</button>` : "-"]])}</div>`;
    window.setMode = async () => { await api("/api/system/mode", "POST", { mode: document.getElementById("mode").value }); render(); };
    window.stopSys = async () => { await api("/api/system/stop", "POST", { reason: "前端模拟急停/报警" }); render(); };
    window.resumeSys = async () => { await api("/api/system/resume", "POST", {}); render(); };
    window.issue = async () => { const r = await api("/api/issuance", "POST", { suggestion_id: parseInt(document.getElementById("sid").value), approved: true }); document.getElementById("out").textContent = JSON.stringify(r, null, 2); render(); };
    window.rollback = async (id) => { await api(`/api/issuance/${id}/rollback`, "POST", {}); render(); };
  },
  async LLM工作台() {
    const list = await api("/api/knowledge");
    main.innerHTML = `<div class="card"><h2>LLM 兜底工作台（本地知识检索 · 不直接控线）</h2>
      <p class="warn">本工作台只返回证据与诊断报告，不写入 PLC。任何生产调整仍须走参数优化 → 审批 → 下发管控流程。</p>
      <input id="q" placeholder="如：料温偏低 气泡" style="width:320px"> <button class="primary" onclick="diag()">检索证据并生成诊断</button><pre id="out"></pre>
      <hr><input id="t" placeholder="经验标题"> <input id="c" placeholder="经验内容" style="width:320px"> <button class="primary" onclick="sed()">专家标注沉淀入库</button></div>
      <div class="card">${rows(list, [["标题", "title"], ["分类", "category"], ["来源", "source"], ["内容", "content"]])}</div>`;
    window.diag = async () => { const r = await api("/api/llm/diagnose", "POST", { query: document.getElementById("q").value }); document.getElementById("out").textContent = JSON.stringify(r, null, 2); };
    window.sed = async () => { await api("/api/knowledge", "POST", { title: document.getElementById("t").value, content: document.getElementById("c").value }); render(); };
  },
  async 模型管理() {
    const list = await api("/api/models"), d = await api("/api/models/drift");
    main.innerHTML = `<div class="card"><h2>模型全生命周期</h2><p>漂移代理指标：近期NG率 ${d.recent_ng_rate}，漂移分数 ${d.drift_score}，预警：${d.warning ? "是" : "否"}（${d.note}）</p>
      ${rows(list, [["模型", "name"], ["版本", "version"], ["状态", "status"], ["召回", "recall"], ["误报", "false_alarm"], ["操作", r => r.status === "shadow" ? `<button onclick="promote(${r.id})">影子晋升生产</button>` : `<button onclick="rollbackM(${r.id})">回退到此版本</button>`]])}</div>`;
    window.promote = async (id) => { await api(`/api/models/${id}/promote`, "POST", {}); render(); };
    window.rollbackM = async (id) => { await api(`/api/models/${id}/rollback`, "POST", {}); render(); };
  },
  async 模型验证() {
    const ad = await api("/api/models/adapters"), twin = await api("/api/models/mechanism-twin"), runs = await api("/api/validation/runs");
    const example = JSON.stringify([
      { material_ratio: 1.08, material_temp: 22, core_temp: 45, curing_time: 360, fixture_temp: 40, is_ng: 0, is_high_risk: 0, is_severe: 0 },
      { material_ratio: 1.30, material_temp: 35, core_temp: 70, curing_time: 60, fixture_temp: 60, is_ng: 1, is_high_risk: 1, is_severe: 1 }
    ], null, 2);
    main.innerHTML = `<div class="card"><div class="card-head"><h2>模型验证：适配器与独立验证</h2>${badge("当前适配器：" + ad.active, "info")}</div>
      <p class="note">优化接口已改为走模型适配器：当前为本地规则；训练模型槽位未接入，选中会被后端拒绝，直到提供模型文件、特征清单并通过独立验证。</p>
      ${rows(ad.adapters, [["适配器", "name"], ["类型", "kind"], ["已接入", r => r.loaded ? "是" : "否"], ["当前", r => r.active ? "是" : "否"], ["说明", "description"], ["操作", r => r.loaded && !r.active ? `<button onclick="selectAd('${r.name}')">设为当前</button>` : "-"]])}</div>
      <div class="card"><h3>机理孪生（约束框架，未验证）</h3>
      <p>状态：${twin.status} · 需验证组数：${twin.required_groups} · 趋势一致性要求：≥${(twin.trend_consistency_required * 100).toFixed(0)}% · 归一化误差上限：${twin.normalized_error_max} · 已验证组数：${twin.validated_groups} · 趋势一致性：${twin.trend_consistency === null ? "未验证" : twin.trend_consistency}</p>
      <p class="note">${twin.note}</p></div>
      <div class="card"><h3>跑一次独立验证</h3>
      <p class="note">粘贴冻结验证集 JSON（每条含 5 个工艺参数 + is_ng，is_high_risk / is_severe 可选）。预测 NG 的口径固定为：缺陷概率 ≥0.50 或超出可行域。结论只对这批样本负责。</p>
      <input id="dsname" placeholder="数据集名称，如 2026-11-冻结验证集A" style="width:320px">
      <textarea id="dsjson">${esc(example)}</textarea>
      <div class="toolbar"><button class="primary" onclick="runVal()">运行验证并留存</button></div><pre id="valout"></pre></div>
      <div class="card"><h3>验证记录</h3>${rows(runs, [["ID", "id"], ["适配器", "adapter"], ["数据集", "dataset_name"], ["样本数", "sample_count"], ["严重漏检", "severe_miss"], ["高风险召回", "high_risk_recall"], ["误报率", "false_alarm_rate"], ["结论", r => statusBadge(r.verdict)]])}</div>`;
    window.selectAd = async (name) => { await api("/api/models/adapters/select", "POST", { adapter: name }); render(); };
    window.runVal = async () => {
      try {
        const samples = JSON.parse(document.getElementById("dsjson").value);
        const r = await api("/api/validation/evaluate", "POST", { dataset_name: document.getElementById("dsname").value, samples });
        document.getElementById("valout").textContent = JSON.stringify(r, null, 2); render();
      } catch (e) { document.getElementById("valout").textContent = "失败：" + e.message; }
    };
  },
  async 灯塔运营() {
    const d = await api("/api/lighthouse");
    main.innerHTML = `<div class="card"><h2>灯塔运营</h2><p>权重：质量 ${d.weights.quality} · 原料 ${d.weights.material} · 能耗 ${d.weights.energy}</p>
      <input id="wq" type="number" step="0.1" value="0.5"> <input id="wm" type="number" step="0.1" value="0.3"> <input id="we" type="number" step="0.1" value="0.2">
      <button class="primary" onclick="setw()">调整权重（管理员）</button>
      <p>一次合格率：${(d.quality.first_pass_rate * 100).toFixed(1)}% · 换产记录：${d.changeover.records} 条 · 爬坡缺陷率：${(d.changeover.ramp_defect_rate * 100).toFixed(1)}% · 知识条目：${d.knowledge_items}</p>
      <p>放行门：${JSON.stringify(d.release_gates)}</p>
      <hr><input id="fp" placeholder="原产品"> <input id="tp" placeholder="新产品"> <input id="rb" type="number" placeholder="爬坡台数"> <input id="rd" type="number" placeholder="爬坡缺陷数">
      <button class="primary" onclick="co()">记录换产爬坡</button></div>
      <div class="card"><h3>9 包多线复制包</h3>${rows(d.replication, [["包", "name"], ["状态", "status"], ["备注", "note"]])}</div>`;
    window.setw = async () => { await api("/api/lighthouse/weights", "POST", { quality: parseFloat(document.getElementById("wq").value), material: parseFloat(document.getElementById("wm").value), energy: parseFloat(document.getElementById("we").value) }); render(); };
    window.co = async () => { await api("/api/changeovers", "POST", { from_product: document.getElementById("fp").value, to_product: document.getElementById("tp").value, ramp_boxes: parseInt(document.getElementById("rb").value || 0), ramp_defects: parseInt(document.getElementById("rd").value || 0) }); render(); };
  },
  async 审计() {
    const list = await api("/api/audit");
    main.innerHTML = `<div class="card"><h2>审计日志（只读 · 追加式）</h2><p class="note">审计表无修改/删除接口，任何操作、审批、修正、启停、回退均留痕。</p>${rows(list, [["时间", "created_at"], ["操作人", "actor"], ["动作", "action"], ["对象", "entity"], ["详情", "detail"]])}</div>`;
  }
};
document.getElementById("nav").innerHTML = tabs.map(t => `<button onclick="go('${t}')">${t}</button>`).join("");
window.go = (t) => { current = t; render(); };
(async () => {
  const users = await api("/api/users");
  userSel.innerHTML = users.map(u => `<option value="${u.username}">${u.display_name}（${u.username} · ${u.role}）</option>`).join("");
  userSel.value = "process_engineer";
  userSel.onchange = render;
  render();
})();
