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
from .models import (AuditLog, Box, Changeover, Issuance, KnowledgeItem,
                     ModelVersion, ProcessRecord, ReplicationPack, Setting,
                     Suggestion, ThermalResult, TraceException, User)
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
             "status": b.status} for b in db.query(Box).order_by(Box.id.desc()).limit(200)]


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
             "is_ng": bool(r.is_ng), "reviewed_by": r.reviewed_by}
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
    result = suggest(params, weights_of(db))
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
            "confidence": result["confidence"], "model_note": result["model_note"]}


@app.get("/api/suggestions")
def list_suggestions(db: Session = Depends(get_db)):
    return [{"id": s.id, "box_barcode": s.box_barcode, "defect_probability": s.defect_probability,
             "confidence": s.confidence, "feasible": bool(s.feasible),
             "routed_to_llm": bool(s.routed_to_llm),
             "suggested": {"material_ratio": s.suggested_ratio,
                           "material_temp": s.suggested_material_temp,
                           "core_temp": s.suggested_core_temp,
                           "curing_time": s.suggested_curing_time},
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


# ---------------------------------------------------------------- frontend
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
