"""Seed demo data. Run:  python -m backend.seed   (from repo root)

All data is SIMULATED demo data for the B-line cabinet foaming system.
No real factory data, no secrets.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.app.database import SessionLocal, init_db
from backend.app.models import (Box, KnowledgeItem, ModelVersion,
                                ReplicationPack, Setting, ThermalResult, User)

PACKS = ["配置包", "模型包", "规则包", "知识包", "硬件包", "接口包", "验收包", "培训包", "运维包"]


def main():
    init_db()
    db = SessionLocal()
    if db.query(User).count():
        print("已存在种子数据，跳过（删除 backend/foaming.db 后可重新播种）")
        return
    for username, role, name in [
        ("process_engineer", "process", "工艺工程师"),
        ("quality_inspector", "quality", "质检复核员"),
        ("equipment_engineer", "equipment", "设备/自动化工程师"),
        ("team_leader", "leader", "班组长"),
        ("admin", "admin", "系统管理员"),
    ]:
        db.add(User(username=username, role=role, display_name=name))
    db.add(Setting(key="mode", value="人工确认"))
    db.add(Setting(key="stopped", value="0"))
    db.add(Setting(key="weights", value='{"quality": 0.5, "material": 0.3, "energy": 0.2}'))
    for i, barcode in enumerate(["BX-B-0001", "BX-B-0002", "BX-B-0003"]):
        db.add(Box(barcode=barcode, fixture_no=f"FJ-0{i + 1}", product="BCD-520W",
                   status="ok" if i < 2 else "ng"))
    db.add(ThermalResult(box_barcode="BX-B-0001", grade="A", max_bubble_mm=1.2, bubble_count=2))
    db.add(ThermalResult(box_barcode="BX-B-0002", grade="B", max_bubble_mm=3.0, bubble_count=5))
    db.add(ThermalResult(box_barcode="BX-B-0003", grade="D", max_bubble_mm=12.0,
                         bubble_count=8, is_ng=1))
    for title, category, content, source in [
        ("料温偏低导致欠发泡", "历史缺陷案例",
         "料温低于20℃且模芯温度低于40℃时，箱体边角易出现欠发泡与大气泡；优先检查料温与模芯温度，再核查料比。",
         "历史缺陷案例库"),
        ("固化时间不足的处置", "专家经验",
         "固化时间低于240秒时返修率上升；调整时单次步长不超过60秒，并跟踪后续10台热成像结果。",
         "专家标注"),
        ("发泡参数安全边界", "工艺标准",
         "料比1.00-1.15、料温18-28℃、模芯温度35-55℃、固化时间180-600秒为本地规则可行域；白名单范围更窄，见系统规则。",
         "工艺标准"),
    ]:
        db.add(KnowledgeItem(title=title, category=category, content=content, source=source))
    db.add(ModelVersion(name="发泡质量小模型", version="v2.3", status="production",
                        recall=0.88, false_alarm=0.08))
    db.add(ModelVersion(name="发泡质量小模型", version="v2.4", status="shadow",
                        recall=0.92, false_alarm=0.05))
    for name in PACKS:
        db.add(ReplicationPack(name=name, status="已就绪" if name in ("配置包", "规则包") else "待准备"))
    db.commit()
    print("种子数据已写入（演示数据）")


if __name__ == "__main__":
    main()
