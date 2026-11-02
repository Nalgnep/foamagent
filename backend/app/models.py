"""SQLAlchemy models.

AuditLog is intentionally append-only: the API exposes no update or delete
route for it, and the model has no such helper. Rows are never mutated.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from .database import Base


def _now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)  # process | quality | equipment | leader | admin
    display_name = Column(String, default="")


class Box(Base):
    __tablename__ = "boxes"
    id = Column(Integer, primary_key=True)
    barcode = Column(String, unique=True, nullable=False)
    fixture_no = Column(String, default="")
    product = Column(String, default="BCD-520W")
    status = Column(String, default="online")  # online | ok | ng | intercepted | rework
    created_at = Column(DateTime, default=_now)


class ProcessRecord(Base):
    __tablename__ = "process_records"
    id = Column(Integer, primary_key=True)
    box_barcode = Column(String, nullable=False)
    material_ratio = Column(Float, default=1.0)
    material_temp = Column(Float, default=22.0)
    injection_weight = Column(Float, default=0.0)
    injection_pressure = Column(Float, default=0.0)
    fixture_temp = Column(Float, default=40.0)
    core_temp = Column(Float, default=45.0)
    curing_time = Column(Float, default=0.0)
    env_temp = Column(Float, default=25.0)
    env_humidity = Column(Float, default=55.0)
    created_at = Column(DateTime, default=_now)


class ThermalResult(Base):
    __tablename__ = "thermal_results"
    id = Column(Integer, primary_key=True)
    box_barcode = Column(String, nullable=False)
    grade = Column(String, default="A")  # A | B | C | D
    max_bubble_mm = Column(Float, default=0.0)
    bubble_count = Column(Integer, default=0)
    is_ng = Column(Integer, default=0)
    reviewed_by = Column(String, default="")
    review_note = Column(String, default="")
    created_at = Column(DateTime, default=_now)


class TraceException(Base):
    __tablename__ = "trace_exceptions"
    id = Column(Integer, primary_key=True)
    barcode = Column(String, default="")
    fixture_no = Column(String, default="")
    kind = Column(String, nullable=False)  # duplicate | missing | conflict | out_of_order
    status = Column(String, default="待确认/关联异常")
    detail = Column(String, default="")
    resolved_by = Column(String, default="")
    created_at = Column(DateTime, default=_now)


class Suggestion(Base):
    __tablename__ = "suggestions"
    id = Column(Integer, primary_key=True)
    box_barcode = Column(String, default="")
    product = Column(String, default="BCD-520W")
    defect_probability = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    feasible = Column(Integer, default=1)
    routed_to_llm = Column(Integer, default=0)
    suggested_ratio = Column(Float, default=1.0)
    suggested_material_temp = Column(Float, default=22.0)
    suggested_core_temp = Column(Float, default=45.0)
    suggested_curing_time = Column(Float, default=0.0)
    objective_score = Column(Float, default=0.0)
    status = Column(String, default="pending")  # pending | approved | rejected | issued | rolled_back
    created_at = Column(DateTime, default=_now)


class Issuance(Base):
    __tablename__ = "issuances"
    id = Column(Integer, primary_key=True)
    suggestion_id = Column(Integer, ForeignKey("suggestions.id"))
    mode = Column(String, default="人工确认")
    checks_json = Column(Text, default="{}")
    status = Column(String, default="blocked")  # blocked | issued | rolled_back | stopped
    plc_receipt = Column(String, default="")
    created_at = Column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    actor = Column(String, default="system")
    action = Column(String, nullable=False)
    entity = Column(String, default="")
    detail = Column(String, default="")
    created_at = Column(DateTime, default=_now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    category = Column(String, default="工艺标准")
    content = Column(Text, default="")
    source = Column(String, default="")
    created_at = Column(DateTime, default=_now)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    status = Column(String, default="shadow")  # production | shadow | retired
    recall = Column(Float, default=0.0)
    false_alarm = Column(Float, default=0.0)
    drift_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_now)


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    id = Column(Integer, primary_key=True)
    adapter = Column(String, default="rules")
    dataset_name = Column(String, default="")
    sample_count = Column(Integer, default=0)
    severe_miss = Column(Integer, default=0)
    high_risk_recall = Column(Float, nullable=True)
    false_alarm_rate = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)
    verdict = Column(String, default="")
    detail_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=_now)


class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, default="")


class Changeover(Base):
    __tablename__ = "changeovers"
    id = Column(Integer, primary_key=True)
    from_product = Column(String, default="")
    to_product = Column(String, default="")
    ramp_boxes = Column(Integer, default=0)
    ramp_defects = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)


class ReplicationPack(Base):
    __tablename__ = "replication_packs"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(String, default="待准备")  # 待准备 | 已就绪 | 已复制
    note = Column(String, default="")
