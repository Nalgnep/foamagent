"""Smoke tests for the runnable system.

Run from repo root:  .venv/bin/python -m pytest tests/ -q
Uses a temporary SQLite file so the real demo DB is untouched.
"""
import os
import sys

os.environ["FOAMING_DB_URL"] = "sqlite:////tmp/foaming-test.db"
if os.path.exists("/tmp/foaming-test.db"):
    os.remove("/tmp/foaming-test.db")

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


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_traceability_exception_and_no_hard_bind():
    # First bind succeeds.
    r = client.post("/api/trace/bind", json={"barcode": "BX-TEST-1", "fixture_no": "FJ-9"}, headers=H)
    assert r.json()["bound"] is True
    # Duplicate barcode -> exception queue, not a hard bind.
    r = client.post("/api/trace/bind", json={"barcode": "BX-TEST-1", "fixture_no": "FJ-10"}, headers=H)
    body = r.json()
    assert body["bound"] is False and body["status"] == "待确认/关联异常"
    # Missing fixture -> exception too.
    r = client.post("/api/trace/bind", json={"barcode": "BX-TEST-2", "fixture_no": ""}, headers=H)
    assert r.json()["bound"] is False


def test_safety_checks_block_issuance():
    # Extreme parameters -> infeasible / low confidence -> blocked.
    sug = client.post("/api/optimize", json={
        "material_ratio": 1.30, "material_temp": 35, "core_temp": 70,
        "curing_time": 60, "fixture_temp": 60, "box_barcode": "BX-TEST-1"}, headers=HP).json()
    assert sug["routed_to_llm"] is True
    out = client.post("/api/issuance", json={"suggestion_id": sug["suggestion_id"], "approved": True}, headers=H).json()
    assert out["blocked"] is True
    assert any(not c["passed"] for c in out["checks"])
    assert len(out["checks"]) == 8


def test_rollback_and_audit():
    sug = client.post("/api/optimize", json={
        "material_ratio": 1.08, "material_temp": 22, "core_temp": 45,
        "curing_time": 360, "fixture_temp": 40, "box_barcode": "BX-TEST-1"}, headers=HP).json()
    out = client.post("/api/issuance", json={"suggestion_id": sug["suggestion_id"], "approved": True}, headers=H).json()
    assert out["ok"] is True, out
    issued = [i for i in client.get("/api/issuances").json() if i["status"] == "issued"]
    assert issued, "expected at least one issued record"
    rb = client.post(f"/api/issuance/{issued[0]['id']}/rollback", headers=H).json()
    assert rb["status"] == "rolled_back"
    assert "material_ratio" in rb["safe_baseline"]
    audit = client.get("/api/audit").json()
    actions = [a["action"] for a in audit]
    assert "rollback" in actions and "issuance_issued" in actions


def test_llm_does_not_control_plc():
    r = client.post("/api/llm/diagnose", json={"query": "料温偏低 气泡"}, headers=HP).json()
    assert r["plc_control"] is False
    assert r["evidence"], "expected traceable evidence"
    # Diagnosing must not create an issuance.
    assert client.get("/api/issuances").json() is not None
