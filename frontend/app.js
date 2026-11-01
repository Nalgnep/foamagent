const tabs = ["驾驶舱", "热成像", "追溯", "参数优化", "下发管控", "LLM工作台", "模型管理", "灯塔运营", "审计"];
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
function rows(list, cols) {
  if (!list.length) return "<p class='note'>暂无数据</p>";
  return "<table><tr>" + cols.map(c => `<th>${c[0]}</th>`).join("") + "</tr>" +
    list.map(r => "<tr>" + cols.map(c => `<td>${esc(typeof c[1] === "function" ? c[1](r) : r[c[1]])}</td>`).join("") + "</tr>").join("") + "</table>";
}
async function render() {
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("active", b.textContent === current));
  try { await views[current](); } catch (e) { main.innerHTML = `<div class="card warn">请求失败：${esc(e.message)}<br>请先确认后端已启动且已选择演示用户。</div>`; }
}
const views = {
  async 驾驶舱() {
    const d = await api("/api/dashboard"), s = await api("/api/system/state");
    main.innerHTML = `<div class="card"><h2>驾驶舱</h2><div class="grid">
      <div class="kpi">箱体数<b>${d.kpis.boxes}</b></div><div class="kpi">热成像检测<b>${d.kpis.thermal_checked}</b></div>
      <div class="kpi">NG数<b>${d.kpis.ng_count}</b></div><div class="kpi">一次合格率<b>${(d.kpis.first_pass_rate * 100).toFixed(1)}%</b></div>
      <div class="kpi">追溯异常待确认<b>${d.kpis.trace_exceptions_open}</b></div><div class="kpi">已下发<b>${d.kpis.issued_count}</b></div>
      <div class="kpi">知识条目<b>${d.kpis.knowledge_items}</b></div><div class="kpi">当前模式<b>${d.kpis.mode}</b></div></div>
      <p>系统状态：${s.stopped ? "已停止（异常）" : "正常"} · 生产模型：${d.kpis.production_model || "-"}</p>
      <p>闭环：${d.closed_loop.join(" → ")}</p>
      <p class="note">协议基线：${JSON.stringify(d.protocol_baseline)}</p></div>`;
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
