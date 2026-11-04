"""Foaming process intelligent agent — management system API.

Design contract (from the Chengdu B-line technical agreement):
  * Closed loop: perception -> quality judgement -> analysis ->
    parameter suggestion / controlled issuance -> effect verification ->
    knowledge sedimentation.
  * The LLM workbench NEVER writes to a PLC. Only the issuance endpoint
    writes (simulated) PLC receipts, and only after all 8 safety checks
    pass. Search for "PLC" in this file to audit that claim.
  * Traceability exceptions are never hard-bound by time proximity.
  * AuditLog has no update/delete endpoint (append-only by design).

Demo authentication: pass ``X-User: <username>`` with a seeded demo user
(process_engineer, quality_inspector, equipment_engineer, team_leader,
admin). This is NOT production authentication; see LIMITATIONS.md.
"""
import json
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .model_interface import (TWIN, evaluate_validation, get_adapter,
                              get_adapters)
from .models import (AuditLog, Box, Changeover, Issuance, KnowledgeItem,
                     ModelVersion, ProcessRecord, ReplicationPack, Setting,
                     Suggestion, ThermalResult, TraceException, User,
                     ValidationRun)
from .rules import (SAFE_BASELINE, WHITELIST, grade_thermal, predict,
                    safety_checks, suggest, is_out_of_distribution)

app = FastAPI(title="成都B线发泡工艺智能体管理系统", version="1.0.0")
init_db()

ROLE_PERMISSIONS = {
    "process": ["suggest", "approve", "issue", "rollback", "knowledge", "model"],
    "quality": ["review", "knowledge"],
    "equipment": ["issue", "rollback", "model"],
    "leader": ["approve", "issue", "rollback"],
    "admin": ["suggest", "approve", "issue", "rollback", "review", "knowledge", "model", "admin"],
}


def audit(db, actor, action, entity, detail=""):
    db.add(AuditLog(actor=actor, action=action, entity=entity, detail=str(detail)))
    db.commit()


def current_user(db: Session, x_user: str | None):
    if not x_user:
        return None
    return db.query(User).filter(User.username == x_user).first()


def require(db: Session, x_user: str | None, permission: str):
    user = current_user(db, x_user)
    if not user:
        raise HTTPException(401, "请通过 X-User 传入演示用户，例如 process_engineer")
    if permission not in ROLE_PERMISSIONS.get(user.role, []):
        raise HTTPException(403, f"角色 {user.role} 无权限执行 {permission}")
    return user


def get_setting(db, key, default):
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def set_setting(db, key, value):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def weights_of(db):
    try:
        return json.loads(get_setting(db, "weights", '{"quality": 0.5, "material": 0.3, "energy": 0.2}'))
    except Exception:
        return {"quality": 0.5, "material": 0.3, "energy": 0.2}


# ---------------------------------------------------------------- health
@app.get("/api/health")
def health():
    return {"status": "ok", "system": "成都B线发泡工艺智能体管理系统",
            "data_note": "演示数据（模拟），非真实产线数据；PLC 为模拟回执"}


# ---------------------------------------------------------------- dashboard
@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    boxes = db.query(Box).count()
    ng = db.query(ThermalResult).filter(ThermalResult.is_ng == 1).count()
    total_thermal = db.query(ThermalResult).count()
    exceptions = db.query(TraceException).filter(
        TraceException.status == "待确认/关联异常").count()
    issued = db.query(Issuance).filter(Issuance.status == "issued").count()
    knowledge = db.query(KnowledgeItem).count()
    production = db.query(ModelVersion).filter(ModelVersion.status == "production").first()
    return {
        "kpis": {
            "boxes": boxes, "thermal_checked": total_thermal, "ng_count": ng,
            "first_pass_rate": round(1 - ng / total_thermal, 4) if total_thermal else 1.0,
            "trace_exceptions_open": exceptions, "issued_count": issued,
            "knowledge_items": knowledge,
            "production_model": f"{production.name} {production.version}" if production else None,
            "mode": get_setting(db, "mode", "人工确认"),
        },
        "closed_loop": ["在线感知", "质量判定", "工艺分析", "参数建议/受控下发", "效果验证", "知识沉淀"],
        "protocol_baseline": {"thermal_association": "≥99%", "severe_miss": "0",
                              "false_alarm": "≤10%", "trace_association": "≥99%",
                              "high_risk_recall": "≥85%", "rag_top3": "≥95%"},
    }


# ---------------------------------------------------------------- boxes / process / thermal
@app.get("/api/boxes")
def list_boxes(db: Session = Depends(get_db)):
    return [{"barcode": b.barcode, "fixture_no": b.fixture_no, "product": b.product,
             "status": b.status, "created_at": str(b.created_at)}
            for b in db.query(Box).order_by(Box.id.desc()).limit(200)]


@app.post("/api/boxes")
def create_box(payload: dict, db: Session = Depends(get_db),
               x_user: str | None = Header(None)):
    if db.query(Box).filter(Box.barcode == payload["barcode"]).first():
        raise HTTPException(409, "箱体条码已存在")
    box = Box(barcode=payload["barcode"], fixture_no=payload.get("fixture_no", ""),
              product=payload.get("product", "BCD-520W"))
    db.add(box); db.commit()
    audit(db, x_user or "system", "box_online", box.barcode, f"夹具 {box.fixture_no}")
    return {"ok": True, "barcode": box.barcode}


@app.post("/api/process-records")
def add_process(payload: dict, db: Session = Depends(get_db)):
    rec = ProcessRecord(**{k: payload[k] for k in payload
                           if k in ProcessRecord.__table__.columns.keys()})
    db.add(rec); db.commit()
    return {"ok": True, "id": rec.id}


@app.post("/api/thermal-results")
def add_thermal(payload: dict, db: Session = Depends(get_db),
                x_user: str | None = Header(None)):
    grade, ng = grade_thermal(payload.get("max_bubble_mm", 0), payload.get("bubble_count", 0))
    row = ThermalResult(box_barcode=payload["box_barcode"], grade=grade,
                        max_bubble_mm=payload.get("max_bubble_mm", 0),
                        bubble_count=payload.get("bubble_count", 0), is_ng=1 if ng else 0)
    db.add(row)
    box = db.query(Box).filter(Box.barcode == row.box_barcode).first()
    if box:
        box.status = "intercepted" if ng else "ok"
    db.commit()
    audit(db, x_user or "system", "thermal_check", row.box_barcode,
          f"等级 {grade}，NG={'是' if ng else '否'}（五面检测，留存≥3年为制度要求）")
    return {"ok": True, "grade": grade, "is_ng": ng,
            "action": "声光报警 + PLC NG信号 + 自动拦截" if ng else "放行"}


@app.post("/api/thermal-results/{rid}/review")
def review_thermal(rid: int, payload: dict, db: Session = Depends(get_db),
                   x_user: str | None = Header(None)):
    require(db, x_user, "review")
    row = db.query(ThermalResult).get(rid)
    if not row:
        raise HTTPException(404, "未找到检测结果")
    row.reviewed_by = x_user or ""; row.review_note = payload.get("note", "")
    db.commit()
    audit(db, x_user, "thermal_review", row.box_barcode, row.review_note)
    return {"ok": True, "reviewed_by": row.reviewed_by}


@app.get("/api/thermal-results")
def list_thermal(db: Session = Depends(get_db)):
    return [{"id": r.id, "box_barcode": r.box_barcode, "grade": r.grade,
             "max_bubble_mm": r.max_bubble_mm, "bubble_count": r.bubble_count,
             "is_ng": bool(r.is_ng), "reviewed_by": r.reviewed_by, "created_at": str(r.created_at)}
            for r in db.query(ThermalResult).order_by(ThermalResult.id.desc()).limit(200)]


# ---------------------------------------------------------------- traceability
@app.post("/api/trace/bind")
def trace_bind(payload: dict, db: Session = Depends(get_db),
               x_user: str | None = Header(None)):
    """Multi-condition binding. Any anomaly -> exception queue, never hard-bound."""
    barcode = payload.get("barcode", "")
    fixture = payload.get("fixture_no", "")
    reason = None
    if not barcode or not fixture:
        reason = ("missing", "条码或夹具号缺失")
    elif db.query(Box).filter(Box.barcode == barcode).first():
        reason = ("duplicate", f"条码 {barcode} 已绑定，疑似重复扫码")
    elif db.query(Box).filter(Box.fixture_no == fixture, Box.status != "intercepted").first():
        reason = ("conflict", f"夹具 {fixture} 已绑定其他在制箱体")
    elif payload.get("out_of_order"):
        reason = ("out_of_order", "时间戳乱序：事件时间早于该夹具上一事件")
    if reason:
        kind, detail = reason
        exc = TraceException(barcode=barcode, fixture_no=fixture, kind=kind, detail=detail)
        db.add(exc); db.commit()
        audit(db, x_user or "system", "trace_exception", barcode, detail)
        return {"ok": False, "bound": False, "exception_id": exc.id,
                "status": "待确认/关联异常", "detail": detail,
                "note": "未硬绑，已进入异常队列等待人工处理"}
    box = Box(barcode=barcode, fixture_no=fixture, product=payload.get("product", "BCD-520W"))
    db.add(box); db.commit()
    audit(db, x_user or "system", "trace_bind", barcode, f"夹具 {fixture}")
    return {"ok": True, "bound": True, "barcode": barcode}


@app.get("/api/trace/exceptions")
def list_exceptions(db: Session = Depends(get_db)):
    return [{"id": e.id, "barcode": e.barcode, "fixture_no": e.fixture_no, "kind": e.kind,
             "status": e.status, "detail": e.detail, "resolved_by": e.resolved_by}
            for e in db.query(TraceException).order_by(TraceException.id.desc()).limit(200)]


@app.post("/api/trace/exceptions/{eid}/resolve")
def resolve_exception(eid: int, payload: dict, db: Session = Depends(get_db),
                      x_user: str | None = Header(None)):
    require(db, x_user, "admin")
    exc = db.query(TraceException).get(eid)
    if not exc:
        raise HTTPException(404, "未找到异常")
    exc.status = "已人工修正"; exc.resolved_by = x_user or ""
    db.commit()
    audit(db, x_user, "trace_manual_correction", exc.barcode,
          f"修正前：{exc.detail}；修正说明：{payload.get('note', '')}")
    return {"ok": True, "status": exc.status}


# ---------------------------------------------------------------- optimization
@app.post("/api/optimize")
def optimize(payload: dict, db: Session = Depends(get_db),
             x_user: str | None = Header(None)):
    params = {k: float(payload[k]) for k in
              ("material_ratio", "material_temp", "core_temp", "curing_time", "fixture_temp")
              if k in payload}
    adapter_name = get_setting(db, "model_adapter", "rules")
    adapter = get_adapter(adapter_name) or get_adapter("rules")
    result = adapter.suggest(params, weights_of(db))
    twin = TWIN.check(params)
    ood = is_out_of_distribution(params)
    routed = bool(not result["feasible"] or result["confidence"] < 0.70 or ood)
    sug = Suggestion(box_barcode=payload.get("box_barcode", ""),
                     product=payload.get("product", "BCD-520W"),
                     defect_probability=result["defect_probability"],
                     confidence=result["confidence"], feasible=1 if result["feasible"] else 0,
                     routed_to_llm=1 if routed else 0,
                     suggested_ratio=result["suggested"]["material_ratio"],
                     suggested_material_temp=result["suggested"]["material_temp"],
                     suggested_core_temp=result["suggested"]["core_temp"],
                     suggested_curing_time=result["suggested"]["curing_time"],
                     objective_score=result["objective_score"])
    db.add(sug); db.commit()
    audit(db, x_user or "system", "optimize", sug.box_barcode,
          f"缺陷概率 {sug.defect_probability}，置信度 {sug.confidence}，转LLM={routed}")
    return {"suggestion_id": sug.id, "routed_to_llm": routed, "out_of_distribution": ood,
            "feasible": result["feasible"], "reasons": result["reasons"],
            "suggested": result["suggested"], "objective_score": result["objective_score"],
            "defect_probability": result["defect_probability"],
            "confidence": result["confidence"], "model_note": result["model_note"],
            "model_adapter": adapter.name, "mechanism_twin": twin}


@app.get("/api/suggestions")
def list_suggestions(db: Session = Depends(get_db)):
    return [{"id": s.id, "box_barcode": s.box_barcode, "defect_probability": s.defect_probability,
             "confidence": s.confidence, "feasible": bool(s.feasible),
             "routed_to_llm": bool(s.routed_to_llm),
             "suggested": {"material_ratio": s.suggested_ratio,
                           "material_temp": s.suggested_material_temp,
                           "core_temp": s.suggested_core_temp,
                           "curing_time": s.suggested_curing_time},
             "objective_score": s.objective_score,
             "status": s.status}
            for s in db.query(Suggestion).order_by(Suggestion.id.desc()).limit(200)]


# ---------------------------------------------------------------- issuance control
@app.get("/api/system/state")
def system_state(db: Session = Depends(get_db)):
    return {"mode": get_setting(db, "mode", "人工确认"),
            "stopped": get_setting(db, "stopped", "0") == "1",
            "safe_baseline": SAFE_BASELINE, "whitelist": WHITELIST}


@app.post("/api/system/mode")
def set_mode(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "admin")
    if payload.get("mode") not in ("关闭", "人工确认", "受控自动"):
        raise HTTPException(400, "模式必须是 关闭 / 人工确认 / 受控自动")
    set_setting(db, "mode", payload["mode"])
    audit(db, x_user, "mode_change", "system", payload["mode"])
    return {"ok": True, "mode": payload["mode"]}


@app.post("/api/system/stop")
def system_stop(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    """E-stop / alarm / data / communication anomaly: stop issuance, keep audit."""
    set_setting(db, "stopped", "1")
    audit(db, x_user or "system", "system_stop", "system", payload.get("reason", "异常停止"))
    return {"ok": True, "stopped": True, "note": "已停止一切新下发，待人工恢复"}


@app.post("/api/system/resume")
def system_resume(db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "admin")
    set_setting(db, "stopped", "0")
    audit(db, x_user, "system_resume", "system", "人工恢复")
    return {"ok": True, "stopped": False}


@app.post("/api/issuance")
def issue(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    user = require(db, x_user, "issue")
    sug = db.query(Suggestion).get(payload["suggestion_id"])
    if not sug:
        raise HTTPException(404, "未找到参数建议")
    mode = get_setting(db, "mode", "人工确认")
    if get_setting(db, "stopped", "0") == "1":
        checks = [{"name": "系统状态", "passed": False, "detail": "系统已停止，禁止下发"}]
        row = Issuance(suggestion_id=sug.id, mode=mode, checks_json=json.dumps(checks),
                       status="stopped")
        db.add(row); db.commit()
        return {"ok": False, "blocked": True, "checks": checks}
    sug_dict = {"material_ratio": sug.suggested_ratio, "material_temp": sug.suggested_material_temp,
                "core_temp": sug.suggested_core_temp, "curing_time": sug.suggested_curing_time,
                "feasible": bool(sug.feasible), "confidence": sug.confidence}
    checks = safety_checks(sug_dict, mode, payload.get("product", sug.product),
                           payload.get("equipment", "B-LINE-FOAM-01"),
                           payload.get("condition", "normal"),
                           payload.get("interlock_ok", True),
                           payload.get("data_complete", True),
                           payload.get("communication_ok", True),
                           payload.get("approved", mode == "人工确认"))
    passed = all(c["passed"] for c in checks)
    status = "issued" if passed else "blocked"
    row = Issuance(suggestion_id=sug.id, mode=mode, checks_json=json.dumps(checks, ensure_ascii=False),
                   status=status,
                   plc_receipt="PLC回执：写入成功（模拟）" if passed else "")
    if passed:
        sug.status = "issued"
    db.add(row); db.commit()
    audit(db, user.username, "issuance_" + status, str(sug.id),
          f"模式 {mode}，8项校验 {'全部通过' if passed else '有未通过项'}")
    return {"ok": passed, "blocked": not passed, "checks": checks,
            "plc_receipt": row.plc_receipt}


@app.post("/api/issuance/{iid}/rollback")
def rollback(iid: int, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "rollback")
    row = db.query(Issuance).get(iid)
    if not row:
        raise HTTPException(404, "未找到下发记录")
    row.status = "rolled_back"
    sug = db.query(Suggestion).get(row.suggestion_id)
    if sug:
        sug.status = "rolled_back"
    db.commit()
    audit(db, x_user, "rollback", str(iid), f"回退至安全基线 {SAFE_BASELINE}")
    return {"ok": True, "safe_baseline": SAFE_BASELINE, "status": "rolled_back"}


@app.get("/api/issuances")
def list_issuances(db: Session = Depends(get_db)):
    return [{"id": r.id, "suggestion_id": r.suggestion_id, "mode": r.mode,
             "status": r.status, "plc_receipt": r.plc_receipt,
             "checks": json.loads(r.checks_json or "{}")}
            for r in db.query(Issuance).order_by(Issuance.id.desc()).limit(200)]


# ---------------------------------------------------------------- LLM workbench (read-only w.r.t. PLC)
@app.post("/api/llm/diagnose")
def llm_diagnose(payload: dict, db: Session = Depends(get_db),
                 x_user: str | None = Header(None)):
    """Local RAG-style retrieval over the seeded knowledge base.

    This endpoint returns evidence and a report. It has no code path to
    any issuance / PLC endpoint; a diagnosis must go through the normal
    approval + issuance flow to affect production.
    """
    query = payload.get("query", "")
    keywords = [w for w in query.replace("，", " ").replace(",", " ").split() if w]
    items = db.query(KnowledgeItem).all()
    scored = []
    for item in items:
        score = sum(1 for w in keywords if w in item.title + item.content)
        if score or not keywords:
            scored.append((score, item))
    scored.sort(key=lambda t: -t[0])
    evidence = [{"id": i.id, "title": i.title, "category": i.category,
                 "source": i.source, "excerpt": i.content[:160]}
                for _, i in scored[:3]]
    report = (f"诊断（本地知识检索，非大模型直接控线）：问题关键词 {keywords}；"
              f"命中证据 {len(evidence)} 条；建议先核查工艺窗口与原料批次，"
              f"再按人工确认流程下发。LLM 诊断本身不写入 PLC。")
    audit(db, x_user or "system", "llm_diagnose", "", query)
    return {"evidence": evidence, "report": report, "plc_control": False}


@app.post("/api/knowledge")
def add_knowledge(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "knowledge")
    item = KnowledgeItem(title=payload["title"], category=payload.get("category", "专家经验"),
                         content=payload.get("content", ""), source=payload.get("source", "专家标注"))
    db.add(item); db.commit()
    audit(db, x_user, "knowledge_sedimentation", item.title, "专家经验沉淀入库")
    return {"ok": True, "id": item.id}


@app.get("/api/knowledge")
def list_knowledge(db: Session = Depends(get_db)):
    return [{"id": k.id, "title": k.title, "category": k.category,
             "source": k.source, "content": k.content}
            for k in db.query(KnowledgeItem).order_by(KnowledgeItem.id.desc()).limit(200)]


# ---------------------------------------------------------------- model lifecycle
@app.get("/api/models")
def list_models(db: Session = Depends(get_db)):
    return [{"id": m.id, "name": m.name, "version": m.version, "status": m.status,
             "recall": m.recall, "false_alarm": m.false_alarm, "drift_score": m.drift_score}
            for m in db.query(ModelVersion).order_by(ModelVersion.id.desc())]


@app.post("/api/models/{mid}/promote")
def promote_model(mid: int, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "model")
    target = db.query(ModelVersion).get(mid)
    if not target or target.status != "shadow":
        raise HTTPException(400, "仅影子运行模型可晋升为生产模型")
    for m in db.query(ModelVersion).filter(ModelVersion.status == "production"):
        m.status = "retired"
    target.status = "production"; db.commit()
    audit(db, x_user, "model_promote", f"{target.name} {target.version}", "影子运行晋升")
    return {"ok": True, "production": target.version}


@app.post("/api/models/{mid}/rollback")
def rollback_model(mid: int, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "model")
    target = db.query(ModelVersion).get(mid)
    if not target:
        raise HTTPException(404, "未找到模型")
    for m in db.query(ModelVersion).filter(ModelVersion.status == "production"):
        m.status = "retired"
    target.status = "production"; db.commit()
    audit(db, x_user, "model_rollback", f"{target.name} {target.version}", "模型回退")
    return {"ok": True, "production": target.version}


@app.get("/api/models/drift")
def drift(db: Session = Depends(get_db)):
    """Drift proxy: recent NG rate vs the production model's false-alarm baseline."""
    total = db.query(ThermalResult).count()
    ng = db.query(ThermalResult).filter(ThermalResult.is_ng == 1).count()
    rate = ng / total if total else 0.0
    drift_score = round(min(1.0, abs(rate - 0.05) * 2), 4)
    return {"recent_ng_rate": round(rate, 4), "drift_score": drift_score,
            "warning": drift_score > 0.15, "note": "漂移代理指标，非训练模型漂移检测"}


# ---------------------------------------------------------------- lighthouse / replication
@app.get("/api/lighthouse")
def lighthouse(db: Session = Depends(get_db)):
    total = db.query(ThermalResult).count()
    ng = db.query(ThermalResult).filter(ThermalResult.is_ng == 1).count()
    cos = db.query(Changeover).all()
    ramp_defects = sum(c.ramp_defects for c in cos)
    ramp_boxes = sum(c.ramp_boxes for c in cos) or 1
    packs = db.query(ReplicationPack).all()
    ready = sum(1 for p in packs if p.status == "已就绪")
    return {
        "weights": weights_of(db),
        "quality": {"first_pass_rate": round(1 - ng / total, 4) if total else 1.0},
        "changeover": {"records": len(cos), "ramp_defect_rate": round(ramp_defects / ramp_boxes, 4)},
        "knowledge_items": db.query(KnowledgeItem).count(),
        "replication": [{"name": p.name, "status": p.status, "note": p.note} for p in packs],
        "release_gates": {
            "追溯关联": "待人工确认（需连续300台抽检）",
            "严重缺陷漏检": "目标 0",
            "复制包就绪": f"{ready}/{len(packs)} 包已就绪",
        },
    }


@app.post("/api/lighthouse/weights")
def set_weights(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "admin")
    w = {"quality": float(payload.get("quality", 0.5)),
         "material": float(payload.get("material", 0.3)),
         "energy": float(payload.get("energy", 0.2))}
    set_setting(db, "weights", json.dumps(w))
    audit(db, x_user, "weights_change", "lighthouse", w)
    return {"ok": True, "weights": w}


@app.post("/api/changeovers")
def add_changeover(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    row = Changeover(from_product=payload.get("from_product", ""),
                     to_product=payload.get("to_product", ""),
                     ramp_boxes=int(payload.get("ramp_boxes", 0)),
                     ramp_defects=int(payload.get("ramp_defects", 0)))
    db.add(row); db.commit()
    audit(db, x_user or "system", "changeover", f"{row.from_product}->{row.to_product}",
          f"爬坡 {row.ramp_boxes} 台，缺陷 {row.ramp_defects} 台")
    return {"ok": True, "id": row.id}


# ---------------------------------------------------------------- audit / users (read-only for audit)
@app.get("/api/audit")
def list_audit(db: Session = Depends(get_db)):
    return [{"id": a.id, "actor": a.actor, "action": a.action, "entity": a.entity,
             "detail": a.detail, "created_at": str(a.created_at)}
            for a in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(300)]


@app.get("/api/users")
def list_users(db: Session = Depends(get_db)):
    return [{"username": u.username, "role": u.role, "display_name": u.display_name}
            for u in db.query(User).all()]


# ---------------------------------------------------------------- model adapters / validation (batch 2, part 1)
@app.get("/api/models/adapters")
def list_adapters(db: Session = Depends(get_db)):
    active = get_setting(db, "model_adapter", "rules")
    return {"active": active, "adapters": get_adapters(active)}


@app.post("/api/models/adapters/select")
def select_adapter(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "model")
    adapter = get_adapter(payload.get("adapter", ""))
    if not adapter:
        raise HTTPException(404, "未找到该模型适配器")
    if not adapter.loaded:
        raise HTTPException(400, "该适配器未接入：需提供模型文件、特征清单与独立验证集后方可启用")
    set_setting(db, "model_adapter", adapter.name)
    audit(db, x_user, "model_adapter_select", adapter.name, "切换生产模型适配器")
    return {"ok": True, "active": adapter.name}


@app.get("/api/models/mechanism-twin")
def mechanism_twin_status():
    return TWIN.validation_status()


@app.post("/api/validation/evaluate")
def validation_evaluate(payload: dict, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    require(db, x_user, "suggest")
    samples = payload.get("samples", [])
    if not isinstance(samples, list) or not samples:
        raise HTTPException(400, "samples 必须是非空列表")
    required = ("material_ratio", "material_temp", "core_temp", "curing_time", "fixture_temp", "is_ng")
    try:
        for s in samples:
            for k in required:
                float(s[k])
    except Exception:
        raise HTTPException(400, f"每条样本必须包含数值字段：{', '.join(required)}")
    adapter_name = get_setting(db, "model_adapter", "rules")
    adapter = get_adapter(adapter_name) or get_adapter("rules")
    metrics = evaluate_validation(adapter, samples)
    run = ValidationRun(adapter=adapter.name, dataset_name=payload.get("dataset_name", ""),
                        sample_count=metrics["sample_count"], severe_miss=metrics["severe_miss"],
                        high_risk_recall=metrics["high_risk_recall"],
                        false_alarm_rate=metrics["false_alarm_rate"],
                        accuracy=metrics["accuracy"], verdict=metrics["verdict"],
                        detail_json=json.dumps(metrics, ensure_ascii=False))
    db.add(run); db.commit()
    audit(db, x_user, "validation_evaluate", str(run.id),
          f"适配器 {adapter.name} · 样本 {metrics['sample_count']} · 结论 {metrics['verdict']}")
    return {"run_id": run.id, "adapter": adapter.name, **metrics}


@app.get("/api/validation/runs")
def validation_runs(db: Session = Depends(get_db)):
    return [{"id": r.id, "adapter": r.adapter, "dataset_name": r.dataset_name,
             "sample_count": r.sample_count, "severe_miss": r.severe_miss,
             "high_risk_recall": r.high_risk_recall, "false_alarm_rate": r.false_alarm_rate,
             "accuracy": r.accuracy, "verdict": r.verdict, "created_at": str(r.created_at)}
            for r in db.query(ValidationRun).order_by(ValidationRun.id.desc()).limit(200)]


# ---------------------------------------------------------------- closed-loop tracking (batch 1)
# Batch 1 adds visibility only: it aggregates rows that already exist
# (boxes, process records, thermal results, suggestions, issuances) into
# a per-box timeline, a protocol-vs-lighthouse KPI table, and an
# issuance-effect comparison. It does NOT invent validation results:
# metrics without an independent validation set are returned as null
# with status 未验证, and model-registry values are labelled as such.
GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}


def _ts(dt):
    return str(dt) if dt else ""


def _issuance_effect(db, row):
    sug = db.query(Suggestion).get(row.suggestion_id) if row.suggestion_id else None
    barcode = sug.box_barcode if sug else ""
    if not barcode:
        return {"issuance_id": row.id, "suggestion_id": row.suggestion_id, "box_barcode": "",
                "status": row.status, "mode": row.mode, "pre_grade": None, "post_grade": None,
                "result": "待关联箱体", "verified": False}
    thermals = db.query(ThermalResult).filter(ThermalResult.box_barcode == barcode).order_by(ThermalResult.id).all()
    pre = [t for t in thermals if t.created_at and row.created_at and t.created_at <= row.created_at]
    post = [t for t in thermals if t.created_at and row.created_at and t.created_at > row.created_at]
    pre_grade = pre[-1].grade if pre else None
    post_grade = post[-1].grade if post else None
    if post_grade is None:
        result = "待验证：下发后暂无热成像结果"
    elif pre_grade is None:
        result = "已有下发后检测，缺下发前对照"
    elif GRADE_RANK.get(post_grade, 9) < GRADE_RANK.get(pre_grade, 9):
        result = "改善：等级好转"
    elif GRADE_RANK.get(post_grade, 9) > GRADE_RANK.get(pre_grade, 9):
        result = "恶化：等级变差，需复核回退"
    else:
        result = "持平：等级未变"
    return {"issuance_id": row.id, "suggestion_id": row.suggestion_id, "box_barcode": barcode,
            "status": row.status, "mode": row.mode, "pre_grade": pre_grade, "post_grade": post_grade,
            "result": result, "verified": bool(pre_grade and post_grade)}


@app.get("/api/boxes/{barcode}/timeline")
def box_timeline(barcode: str, db: Session = Depends(get_db)):
    box = db.query(Box).filter(Box.barcode == barcode).first()
    if not box:
        raise HTTPException(404, "未找到该箱体")
    events = []
    events.append({"stage": "在线感知", "title": "箱体上线", "detail": f"夹具 {box.fixture_no} · 产品 {box.product} · 状态 {box.status}", "created_at": _ts(box.created_at)})
    for r in db.query(ProcessRecord).filter(ProcessRecord.box_barcode == barcode).order_by(ProcessRecord.id):
        events.append({"stage": "在线感知", "title": "工艺参数记录", "detail": f"料比 {r.material_ratio} · 料温 {r.material_temp}℃ · 模芯 {r.core_temp}℃ · 固化 {r.curing_time}s · 夹具 {r.fixture_temp}℃", "created_at": _ts(r.created_at)})
    thermals = db.query(ThermalResult).filter(ThermalResult.box_barcode == barcode).order_by(ThermalResult.id).all()
    for t in thermals:
        detail = f"等级 {t.grade} · 最大气泡 {t.max_bubble_mm}mm · 数量 {t.bubble_count} · NG={'是' if t.is_ng else '否'}"
        if t.reviewed_by:
            detail += f" · 已复核（{t.reviewed_by}：{t.review_note}）"
        events.append({"stage": "质量判定", "title": "热成像检测", "detail": detail, "created_at": _ts(t.created_at)})
    for e in db.query(TraceException).filter(TraceException.barcode == barcode).order_by(TraceException.id):
        events.append({"stage": "追溯", "title": "关联异常", "detail": f"{e.kind} · {e.detail} · 状态 {e.status}", "created_at": _ts(e.created_at)})
    sugs = db.query(Suggestion).filter(Suggestion.box_barcode == barcode).order_by(Suggestion.id).all()
    sug_ids = [s.id for s in sugs]
    for s in sugs:
        events.append({"stage": "工艺分析", "title": "参数建议", "detail": f"缺陷概率 {s.defect_probability} · 置信度 {s.confidence} · 可行域={'是' if s.feasible else '否'} · 转LLM={'是' if s.routed_to_llm else '否'} · 状态 {s.status}", "created_at": _ts(s.created_at)})
    issuances = db.query(Issuance).filter(Issuance.suggestion_id.in_(sug_ids)).order_by(Issuance.id).all() if sug_ids else []
    for row in issuances:
        try:
            checks = json.loads(row.checks_json or "{}")
            passed = f"{sum(1 for c in checks if c.get('passed'))}/{len(checks)} 项通过" if isinstance(checks, list) else ""
        except Exception:
            passed = ""
        events.append({"stage": "参数建议/受控下发", "title": "下发" if row.status == "issued" else f"下发{row.status}",
                       "detail": f"模式 {row.mode} · {passed} · {row.plc_receipt}", "created_at": _ts(row.created_at)})
        eff = _issuance_effect(db, row)
        if eff["post_grade"]:
            events.append({"stage": "效果验证", "title": "下发后效果验证", "detail": f"下发前 {eff['pre_grade']} → 下发后 {eff['post_grade']} · {eff['result']}", "created_at": _ts(row.created_at)})
    stage_order = {"在线感知": 0, "质量判定": 1, "工艺分析": 2, "参数建议/受控下发": 3, "效果验证": 4, "知识沉淀": 5, "追溯": 6}
    events.sort(key=lambda e: (e["created_at"], stage_order.get(e["stage"], 9)))
    has = {e["stage"] for e in events}
    stages = []
    for name in ["在线感知", "质量判定", "工艺分析", "参数建议/受控下发", "效果验证", "知识沉淀"]:
        done = name in has
        note = ""
        if name == "知识沉淀":
            note = "知识库为全局条目，未按箱体关联；需专家将本箱案例标注入库才算沉淀"
            done = False
        stages.append({"stage": name, "done": done, "note": note})
    pending = [s["stage"] for s in stages if not s["done"]]
    return {"box": {"barcode": box.barcode, "fixture_no": box.fixture_no, "product": box.product, "status": box.status},
            "stages": stages, "next_step": pending[0] if pending else "闭环已完成",
            "events": events}


@app.get("/api/kpi/dual-track")
def dual_track(db: Session = Depends(get_db)):
    total = db.query(ThermalResult).count()
    ng = db.query(ThermalResult).filter(ThermalResult.is_ng == 1).count()
    boxes = db.query(Box).count()
    production = db.query(ModelVersion).filter(ModelVersion.status == "production").first()
    recall = production.recall if production else None
    false_alarm = production.false_alarm if production else None
    first_pass = round(1 - ng / total, 4) if total else None
    demo_association = round(total / boxes, 4) if boxes else None
    rows = [
        {"metric": "严重缺陷漏检", "protocol": "0", "lighthouse": "0（与协议一致）", "current": None, "status": "未验证",
         "note": "需冻结独立验证集；当前无独立验证结果，不得以演示 NG 率代替"},
        {"metric": "高风险召回率", "protocol": "≥85%", "lighthouse": "≥92%（供应商拔高目标）", "current": recall, "status": "达标（协议）" if recall is not None and recall >= 0.85 else ("未达协议" if recall is not None else "未验证"),
         "note": "当前值为模型登记召回，非独立验证集结果"},
        {"metric": "误报率", "protocol": "≤10%", "lighthouse": "≤5%（供应商拔高目标）", "current": false_alarm, "status": "达标（协议）" if false_alarm is not None and false_alarm <= 0.10 else ("未达协议" if false_alarm is not None else "未验证"),
         "note": "当前值为模型登记误报，非独立验证集结果"},
        {"metric": "热成像关联率", "protocol": "≥99%", "lighthouse": "—（未单列拔高）", "current": demo_association, "status": "演示口径",
         "note": "演示口径：已检测箱体数/上线箱体数，按条码输入关联，非 ≥100 台连续箱体验收"},
        {"metric": "追溯关联率", "protocol": "≥99%", "lighthouse": "≥99.5%（供应商拔高目标）", "current": None, "status": "未验证",
         "note": "需 ≥300 台连续箱体；当前样本不足且含种子数据"},
        {"metric": "RAG Top3 命中率", "protocol": "≥95%", "lighthouse": "≥98%（供应商拔高目标）", "current": None, "status": "未验证",
         "note": "当前为本地关键词检索，无约定题库测试结果"},
        {"metric": "一次合格率", "protocol": "协议未单列", "lighthouse": "—", "current": first_pass, "status": "演示口径",
         "note": "演示数据，非真实产线合格率"},
    ]
    return {"rows": rows, "production_model": f"{production.name} {production.version}" if production else None,
            "note": "协议基线为技术协议验收口径；灯塔列为供应商拔高目标，不作为验收否决项；current 为 null 即未验证，不得读作达标"}


@app.get("/api/issuances/effects")
def issuance_effects(db: Session = Depends(get_db)):
    rows = db.query(Issuance).order_by(Issuance.id.desc()).limit(200).all()
    return [_issuance_effect(db, r) for r in rows]


@app.post("/api/issuances/{iid}/verify")
def verify_issuance(iid: int, db: Session = Depends(get_db), x_user: str | None = Header(None)):
    if not current_user(db, x_user):
        raise HTTPException(401, "请通过 X-User 传入演示用户")
    row = db.query(Issuance).get(iid)
    if not row:
        raise HTTPException(404, "未找到下发记录")
    eff = _issuance_effect(db, row)
    audit(db, x_user, "effect_verify", str(iid),
          f"下发前 {eff['pre_grade']} → 下发后 {eff['post_grade']} · {eff['result']}")
    return {"ok": True, **eff}


# ---------------------------------------------------------------- frontend
# Vue 3 + Element Plus build (web/dist) takes precedence when present;
# otherwise fall back to the legacy vanilla frontend/ directory.
_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = _ROOT / "web" / "dist" if (_ROOT / "web" / "dist" / "index.html").exists() else _ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
