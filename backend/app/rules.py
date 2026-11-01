"""Deterministic local rules for the runnable system.

IMPORTANT: these are NOT a trained model. They are documented, auditable
scoring / feasibility rules that let the system run end-to-end, be tested,
and be replaced later by a validated trained model + mechanism twin.
Every API response that uses them says so.

Feasible windows (local rules, documented here, not factory secrets):
  material_ratio  1.00 - 1.15
  material_temp   18 - 28 C
  core_temp       35 - 55 C
  curing_time     180 - 600 s
  fixture_temp    30 - 50 C
"""

FEASIBLE = {
    "material_ratio": (1.00, 1.15),
    "material_temp": (18.0, 28.0),
    "core_temp": (35.0, 55.0),
    "curing_time": (180.0, 600.0),
    "fixture_temp": (30.0, 50.0),
}

# Whitelist: product / equipment / condition / parameter ranges.
WHITELIST = {
    "products": ["BCD-520W", "BCD-450W"],
    "equipment": ["B-LINE-FOAM-01", "B-LINE-FOAM-02"],
    "conditions": ["normal", "changeover"],
    "material_ratio": (1.00, 1.12),
    "material_temp": (19.0, 27.0),
    "core_temp": (38.0, 52.0),
    "curing_time": (240.0, 540.0),
}

# Last safe baseline (used by rollback).
SAFE_BASELINE = {
    "material_ratio": 1.08,
    "material_temp": 22.0,
    "core_temp": 45.0,
    "curing_time": 360.0,
}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def grade_thermal(max_bubble_mm, bubble_count):
    """A/B/C/D grading. D, or C with many bubbles, is NG."""
    if max_bubble_mm >= 10 or bubble_count >= 20:
        grade, ng = "D", True
    elif max_bubble_mm >= 5:
        grade, ng = ("C", bubble_count >= 10)
    elif max_bubble_mm >= 2:
        grade, ng = "B", False
    else:
        grade, ng = "A", False
    return grade, ng


def predict(params):
    """Return (defect_probability, confidence, feasible, reasons).

    Penalty grows with distance from the centre of each feasible window,
    plus an interaction penalty when material is cold and core is cold.
    """
    reasons = []
    penalty = 0.0
    centres = {"material_ratio": 1.075, "material_temp": 23.0,
               "core_temp": 45.0, "curing_time": 390.0, "fixture_temp": 40.0}
    scales = {"material_ratio": 0.075, "material_temp": 5.0,
              "core_temp": 10.0, "curing_time": 210.0, "fixture_temp": 10.0}
    feasible = True
    for key, (lo, hi) in FEASIBLE.items():
        v = params.get(key)
        if v is None:
            feasible, reasons = False, reasons + [f"{key} 缺失"]
            continue
        if not (lo <= v <= hi):
            feasible = False
            reasons.append(f"{key}={v} 超出可行域 [{lo}, {hi}]")
        penalty += abs(v - centres[key]) / scales[key] * 0.12
    if params.get("material_temp", 23) < 20 and params.get("core_temp", 45) < 40:
        penalty += 0.15
        reasons.append("料温偏低且模芯温度偏低，存在欠发泡风险")
    if params.get("curing_time", 390) < 240:
        penalty += 0.12
        reasons.append("固化时间偏短")
    defect_probability = round(clamp(0.05 + penalty, 0.01, 0.95), 4)
    confidence = round(clamp(1.0 - penalty, 0.30, 0.98), 4)
    return defect_probability, confidence, feasible, reasons


def is_out_of_distribution(params):
    """Simple OOD rule: any key far outside its feasible window."""
    for key, (lo, hi) in FEASIBLE.items():
        v = params.get(key)
        if v is not None and (v < lo * 0.9 or v > hi * 1.1):
            return True
    return False


def suggest(params, weights):
    """Multi-objective suggestion: move each parameter toward its centre,
    weighted by quality / material / energy weights (weights sum to ~1)."""
    defect_probability, confidence, feasible, reasons = predict(params)
    wq = weights.get("quality", 0.5)
    step = 0.3 + 0.5 * wq  # higher quality weight -> stronger correction
    centres = {"material_ratio": 1.075, "material_temp": 23.0,
               "core_temp": 45.0, "curing_time": 390.0}
    out = {}
    for key, centre in centres.items():
        v = params.get(key, centre)
        out[key] = round(v + (centre - v) * step, 4)
    # Material saving: slightly lower ratio when defect risk is low.
    if defect_probability < 0.15:
        out["material_ratio"] = round(max(1.02, out["material_ratio"] - 0.01 * weights.get("material", 0.3)), 4)
    objective = round(
        wq * (1 - defect_probability)
        + weights.get("material", 0.3) * (1 - out["material_ratio"] / 1.15)
        + weights.get("energy", 0.2) * (1 - out["curing_time"] / 600.0),
        4,
    )
    return {
        "defect_probability": defect_probability,
        "confidence": confidence,
        "feasible": feasible,
        "reasons": reasons,
        "suggested": out,
        "objective_score": objective,
        "model_note": "本地确定性规则（非训练模型），用于可运行系统演示与测试",
    }


def safety_checks(suggestion, mode, product, equipment, condition,
                  interlock_ok, data_complete, communication_ok, approved):
    """Exactly 8 safety checks. Returns list of {name, passed, detail}."""
    s = suggestion
    checks = [
        {"name": "白名单", "passed": product in WHITELIST["products"]
         and equipment in WHITELIST["equipment"]
         and condition in WHITELIST["conditions"],
         "detail": f"产品 {product} / 设备 {equipment} / 工况 {condition}"},
        {"name": "参数范围", "passed": all(
            WHITELIST[k][0] <= s[k] <= WHITELIST[k][1]
            for k in ("material_ratio", "material_temp", "core_temp", "curing_time")),
         "detail": "建议参数均在白名单范围内"},
        {"name": "单次步长", "passed": abs(s["material_ratio"] - SAFE_BASELINE["material_ratio"]) <= 0.05
         and abs(s["material_temp"] - SAFE_BASELINE["material_temp"]) <= 3
         and abs(s["core_temp"] - SAFE_BASELINE["core_temp"]) <= 5,
         "detail": "相对安全基线的单次步长在限值内"},
        {"name": "置信度与可行域", "passed": bool(s.get("feasible")) and s.get("confidence", 0) >= 0.70,
         "detail": f"置信度 {s.get('confidence')}，可行域 {'通过' if s.get('feasible') else '不通过'}"},
        {"name": "联锁与急停", "passed": bool(interlock_ok),
         "detail": "急停未触发、联锁正常" if interlock_ok else "急停/联锁异常，禁止下发"},
        {"name": "数据完整性", "passed": bool(data_complete),
         "detail": "数据完整" if data_complete else "数据缺失/异常，禁止下发"},
        {"name": "通信状态", "passed": bool(communication_ok),
         "detail": "通信正常" if communication_ok else "通信异常，禁止下发"},
        {"name": "模式与审批", "passed": mode in ("人工确认", "受控自动") and bool(approved),
         "detail": f"模式 {mode}，审批 {'已通过' if approved else '未通过'}"},
    ]
    return checks
