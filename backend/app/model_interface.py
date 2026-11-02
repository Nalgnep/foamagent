"""Model adapter interface, mechanism-twin constraint framework, validation.

This is the production-facing seam that batch 2 will use:

* ``/api/optimize`` no longer calls the deterministic rules directly. It
  calls the *active adapter*, which today is the rule adapter. A trained
  model (LightGBM / Stacking or equivalent) is registered as an adapter
  slot, but it is NOT loaded: selecting it is blocked until a model file
  and a feature list are supplied and a validation run passes.
* The mechanism twin here is a constraint framework only (feasible
  windows + physical constraints). It is NOT a validated reduced-order
  model: its trend-consistency / error metrics are None until a
  >=100-group independent validation set is supplied.
* Validation uses a caller-supplied, frozen dataset. Predicted NG is
  defined once, here: defect_probability >= 0.50 OR the sample is
  outside the feasible region (flagged, not silently passed).
  Protocol verdicts are computed from that dataset only; no metric is
  ever back-filled from demo seed data.
"""
from .rules import FEASIBLE, is_out_of_distribution, predict, suggest


class RuleModelAdapter:
    name = "rules"
    kind = "deterministic_rules"
    loaded = True
    description = "本地确定性规则（非训练模型）：可审计、可运行、可被训练模型替换"

    def suggest(self, params, weights):
        result = suggest(params, weights)
        result["model_adapter"] = self.name
        return result

    def predict(self, params):
        defect_probability, confidence, feasible, reasons = predict(params)
        return {"defect_probability": defect_probability, "confidence": confidence,
                "feasible": feasible, "reasons": reasons,
                "out_of_distribution": is_out_of_distribution(params)}


class TrainedModelAdapterSlot:
    name = "trained_lightgbm"
    kind = "trained_model"
    loaded = False
    description = "训练模型槽位（LightGBM/Stacking 或等效模型）：未接入，需提供模型文件、特征清单与独立验证集后方可启用"

    def suggest(self, params, weights):
        raise RuntimeError("训练模型未接入：请先提供模型文件与特征清单，并通过独立验证")

    def predict(self, params):
        raise RuntimeError("训练模型未接入：请先提供模型文件与特征清单，并通过独立验证")


ADAPTERS = [RuleModelAdapter(), TrainedModelAdapterSlot()]


def get_adapters(active_name):
    return [{"name": a.name, "kind": a.kind, "loaded": a.loaded,
             "description": a.description, "active": a.name == active_name}
            for a in ADAPTERS]


def get_adapter(name):
    for a in ADAPTERS:
        if a.name == name:
            return a
    return None


class ConstrainedMechanismTwin:
    """Constraint framework for the mechanism twin.

    Checks the same physical feasible windows as the rules, plus the
    documented cold-material / cold-core interaction. It returns a
    feasibility verdict, never a validated trend prediction.
    """

    def check(self, params):
        violated = []
        for key, (lo, hi) in FEASIBLE.items():
            v = params.get(key)
            if v is None:
                violated.append(f"{key} 缺失")
            elif not (lo <= v <= hi):
                violated.append(f"{key}={v} 超出机理可行域 [{lo}, {hi}]")
        if params.get("material_temp", 23) < 20 and params.get("core_temp", 45) < 40:
            violated.append("料温偏低且模芯温度偏低，机理上存在欠发泡风险")
        return {"feasible": not violated, "constraints_violated": violated,
                "feasible_region": {k: list(v) for k, v in FEASIBLE.items()}}

    def validation_status(self):
        return {
            "kind": "reduced_order_constraint_framework",
            "status": "未验证",
            "required_groups": 100,
            "trend_consistency_required": 0.90,
            "normalized_error_max": 0.10,
            "validated_groups": 0,
            "trend_consistency": None,
            "normalized_error": None,
            "note": "机理孪生尚未用 ≥100 组典型工况独立验证数据验证，趋势一致性与归一化误差均为 null，不得读作已验证",
        }


TWIN = ConstrainedMechanismTwin()


def evaluate_validation(adapter, samples):
    """Evaluate one frozen dataset against protocol thresholds.

    samples: [{material_ratio, material_temp, core_temp, curing_time,
    fixture_temp, is_ng (0/1), is_high_risk (0/1, optional),
    is_severe (0/1, optional)}]
    """
    tp = fp = tn = fn = 0
    tp_high = fn_high = 0
    severe_miss = 0
    for s in samples:
        params = {k: float(s[k]) for k in
                  ("material_ratio", "material_temp", "core_temp", "curing_time", "fixture_temp")}
        pred = adapter.predict(params)
        predicted_ng = bool(pred["defect_probability"] >= 0.50 or not pred["feasible"])
        is_ng = bool(s.get("is_ng", 0))
        if is_ng and predicted_ng:
            tp += 1
        elif is_ng and not predicted_ng:
            fn += 1
        elif not is_ng and predicted_ng:
            fp += 1
        else:
            tn += 1
        if s.get("is_high_risk", 0):
            if predicted_ng:
                tp_high += 1
            else:
                fn_high += 1
        if s.get("is_severe", 0) and not predicted_ng:
            severe_miss += 1
    total = len(samples)
    recall = round(tp_high / (tp_high + fn_high), 4) if (tp_high + fn_high) else None
    false_alarm = round(fp / (fp + tn), 4) if (fp + tn) else None
    accuracy = round((tp + tn) / total, 4) if total else None
    if recall is None or false_alarm is None:
        verdict = "未验证：样本中缺少高风险或非 NG 对照，无法计算完整指标"
    elif severe_miss == 0 and recall >= 0.85 and false_alarm <= 0.10:
        verdict = "通过协议基线"
    else:
        verdict = "未通过协议基线"
    return {"sample_count": total, "severe_miss": severe_miss,
            "high_risk_recall": recall, "false_alarm_rate": false_alarm,
            "accuracy": accuracy, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "predicted_ng_threshold": "defect_probability >= 0.50 或超出可行域",
            "verdict": verdict}
