"""Batch 1 tests: closed-loop timeline, dual-track KPI, issuance effects.

Uses its own temp DB when run standalone. When run in the full suite,
pytest imports this file first, so the engine binds to this DB and the
smoke tests then share it (seed is idempotent); when smoke runs first,
this file reuses the smoke DB instead of deleting a live file.
"""
import os
import sys

if "FOAMING_DB_URL" not in os.environ:
    os.environ["FOAMING_DB_URL"] = "sqlite:////tmp/foaming-batch1.db"
    if os.path.exists("/tmp/foaming-batch1.db"):
        os.remove("/tmp/foaming-batch1.db")

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


def test_timeline_for_seeded_box():
    r = client.get("/api/boxes/BX-B-0001/timeline")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["box"]["barcode"] == "BX-B-0001"
    stages = {s["stage"]: s["done"] for s in body["stages"]}
    assert stages["在线感知"] is True
    assert stages["质量判定"] is True
    # Knowledge is global, not per-box, so it must stay pending, honestly.
    assert stages["知识沉淀"] is False
    assert body["next_step"]
    assert any(e["stage"] == "质量判定" for e in body["events"])


def test_timeline_missing_box_is_404():
    assert client.get("/api/boxes/NO-SUCH-BOX/timeline").status_code == 404


def test_dual_track_does_not_fabricate_validation():
    body = client.get("/api/kpi/dual-track").json()
    rows = {r["metric"]: r for r in body["rows"]}
    # Metrics without an independent validation set must be null / 未验证.
    assert rows["严重缺陷漏检"]["current"] is None
    assert rows["严重缺陷漏检"]["status"] == "未验证"
    assert rows["追溯关联率"]["current"] is None
    assert rows["RAG Top3 命中率"]["current"] is None
    # Registry values are present but labelled as registry, not validation.
    assert rows["高风险召回率"]["current"] == 0.88
    assert "登记" in rows["高风险召回率"]["note"]


def test_issuance_effect_flow():
    sug = client.post("/api/optimize", json={
        "material_ratio": 1.08, "material_temp": 22, "core_temp": 45,
        "curing_time": 360, "fixture_temp": 40, "box_barcode": "BX-B-0001"}, headers=HP).json()
    out = client.post("/api/issuance", json={"suggestion_id": sug["suggestion_id"], "approved": True}, headers=H).json()
    assert out["ok"] is True
    effects = client.get("/api/issuances/effects").json()
    mine = [e for e in effects if e["box_barcode"] == "BX-B-0001"]
    assert mine, "expected an effect row for the issued suggestion"
    # No post-issuance thermal yet in this flow, so it must say 待验证.
    assert "待验证" in mine[0]["result"]
    v = client.post(f"/api/issuances/{mine[0]['issuance_id']}/verify", headers=HP).json()
    assert v["ok"] is True and v["verified"] is False
