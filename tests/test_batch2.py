"""Batch 2 (part 1) tests: model adapters, mechanism twin, validation.

Reuses the batch-1 test setup: when run in the full suite the engine is
already bound and seeded; standalone it binds to its own temp DB.
"""
import os
import sys

if "FOAMING_DB_URL" not in os.environ:
    os.environ["FOAMING_DB_URL"] = "sqlite:////tmp/foaming-batch2.db"
    if os.path.exists("/tmp/foaming-batch2.db"):
        os.remove("/tmp/foaming-batch2.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.database import init_db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.seed import main as seed_main  # noqa: E402

init_db()
seed_main()
client = TestClient(app)
H = {"X-User": "admin"}
HP = {"X-User": "process_engineer"}


def test_adapters_default_is_rules_and_trained_slot_blocked():
    body = client.get("/api/models/adapters").json()
    assert body["active"] == "rules"
    by_name = {a["name"]: a for a in body["adapters"]}
    assert by_name["rules"]["loaded"] is True
    assert by_name["trained_lightgbm"]["loaded"] is False
    r = client.post("/api/models/adapters/select", json={"adapter": "trained_lightgbm"}, headers=H)
    assert r.status_code == 400
    # Active adapter must still be rules after the blocked selection.
    assert client.get("/api/models/adapters").json()["active"] == "rules"


def test_mechanism_twin_is_unvalidated_not_fabricated():
    body = client.get("/api/models/mechanism-twin").json()
    assert body["status"] == "未验证"
    assert body["trend_consistency"] is None
    assert body["validated_groups"] == 0


def test_optimize_goes_through_adapter_and_reports_twin():
    r = client.post("/api/optimize", json={
        "material_ratio": 1.08, "material_temp": 22, "core_temp": 45,
        "curing_time": 360, "fixture_temp": 40, "box_barcode": "BX-B-0001"}, headers=HP).json()
    assert r["model_adapter"] == "rules"
    assert r["mechanism_twin"]["feasible"] is True


def test_validation_evaluate_and_runs():
    samples = [
        {"material_ratio": 1.08, "material_temp": 22, "core_temp": 45, "curing_time": 360,
         "fixture_temp": 40, "is_ng": 0, "is_high_risk": 0, "is_severe": 0},
        {"material_ratio": 1.30, "material_temp": 35, "core_temp": 70, "curing_time": 60,
         "fixture_temp": 60, "is_ng": 1, "is_high_risk": 1, "is_severe": 1},
    ]
    body = client.post("/api/validation/evaluate",
                       json={"dataset_name": "batch2-test", "samples": samples}, headers=HP).json()
    assert body["sample_count"] == 2
    assert body["severe_miss"] == 0
    assert body["high_risk_recall"] == 1.0
    assert "run_id" in body
    runs = client.get("/api/validation/runs").json()
    assert any(r["id"] == body["run_id"] for r in runs)


def test_validation_rejects_bad_dataset():
    r = client.post("/api/validation/evaluate", json={"dataset_name": "x", "samples": []}, headers=HP)
    assert r.status_code == 400
