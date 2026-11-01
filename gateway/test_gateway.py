"""Gateway tests: no real PLC required (MockPLCClient only)."""

import pytest

from gateway.client import MockPLCClient
from gateway.config import GatewayConfig, Point
from gateway.gateway import AuditLog, Gateway, GatewayError, WriteRejected
from gateway.types import decode_value, encode_value


def _points():
    return [
        Point(name="temp", symbol="DB.Temp", type="Real", access="read"),
        Point(name="setpoint", symbol="DB.Setpoint", type="Real", access="read_write",
              min_value=15.0, max_value=45.0, max_step=2.0, requires_approval=True),
        Point(name="flag", symbol="DB.Flag", type="Bool", access="read"),
    ]


def _gateway(**overrides):
    tags = {
        "DB.Temp": encode_value("Real", 32.0),
        "DB.Setpoint": encode_value("Real", 32.0),
        "DB.Flag": encode_value("Bool", True),
    }
    client = MockPLCClient(tags)
    kwargs = {"points": _points(), "writes_enabled": True}
    kwargs.update(overrides)
    config = GatewayConfig(**kwargs)
    gw = Gateway(config, client, AuditLog())
    gw.connect()
    return gw, client


def test_type_roundtrip():
    for type_name, value in [
        ("Bool", True), ("Int", -123), ("DInt", 123456), ("Real", 12.5),
        ("Word", 65000), ("Byte", 7),
    ]:
        assert decode_value(type_name, encode_value(type_name, value)) == pytest.approx(value) if isinstance(value, float) else decode_value(type_name, encode_value(type_name, value)) == value
    assert decode_value("String", encode_value("String", "BX-1", string_length=24)) == "BX-1"


def test_batch_read_and_chunking():
    gw, _ = _gateway(batch_size=2)
    values = gw.read_points()
    assert values["temp"] == pytest.approx(32.0)
    assert values["flag"] is True


def test_read_unknown_point_rejected():
    gw, _ = _gateway()
    with pytest.raises(GatewayError):
        gw.read_points(["no_such_point"])


def test_write_read_only_rejected_and_not_sent():
    gw, client = _gateway()
    before = client.write_calls
    with pytest.raises(WriteRejected):
        gw.write_point("temp", 33.0, approved=True)
    assert client.write_calls == before


def test_write_range_step_approval():
    gw, _ = _gateway()
    gw.read_points(["setpoint"])  # last read = 32.0
    with pytest.raises(WriteRejected):
        gw.write_point("setpoint", 50.0, approved=True)  # above max
    with pytest.raises(WriteRejected):
        gw.write_point("setpoint", 33.0, approved=False)  # approval required
    with pytest.raises(WriteRejected):
        gw.write_point("setpoint", 35.0, approved=True)  # step 3.0 > 2.0
    out = gw.write_point("setpoint", 33.5, approved=True)
    assert out["value"] == 33.5


def test_writes_disabled():
    gw, client = _gateway(writes_enabled=False)
    with pytest.raises(WriteRejected):
        gw.write_point("setpoint", 33.0, approved=True)
    assert client.write_calls == 0


def test_read_reconnects_after_link_failure():
    gw, client = _gateway(max_retries=3, backoff_s=0.0)
    client.fail_reads = 2
    values = gw.read_points(["temp"])
    assert values["temp"] == pytest.approx(32.0)
    assert client.read_calls >= 3


def test_write_failure_is_not_retried():
    gw, client = _gateway()
    client.fail_writes = 5  # more failures than any retry budget
    with pytest.raises(GatewayError):
        gw.write_point("setpoint", 33.0, approved=True)
    assert client.write_calls == 1  # exactly one attempt
    # The audit trail must record the unknown state.
    assert any(e.get("status") == "unknown" for e in gw.audit.entries)


def test_audit_is_append_only():
    gw, _ = _gateway()
    gw.read_points(["temp"])
    gw.write_point("setpoint", 33.0, approved=True)
    assert len(gw.audit.entries) >= 3
    assert not hasattr(gw.audit, "delete")
