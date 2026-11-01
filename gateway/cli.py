"""Gateway CLI.

Examples (mock PLC, no CPU needed):

    python -m gateway.cli --mock --read-all
    python -m gateway.cli --mock --poll --cycles 3
    python -m gateway.cli --mock --write interface_material_temp_setpoint 32.0 --approved --actor process_engineer

Real PLC (password ONLY via environment, never on the command line):

    S7_HOST=192.168.1.10 S7_PASSWORD='...' GATEWAY_WRITES_ENABLED=true \
        python -m gateway.cli --config gateway/points.json --read-all

The CLI exits non-zero on a rejected write or a failed read, so it
can be used in scripts and in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from .client import MockPLCClient, S7CommPlusPLCClient
from .config import GatewayConfig, load_points
from .gateway import AuditLog, Gateway, GatewayError, WriteRejected
from .types import encode_value


def _mock_client() -> MockPLCClient:
    tags = {
        "DataBlocksGlobal.DB_Foaming.MaterialRatio": encode_value("Real", 1.0),
        "DataBlocksGlobal.DB_Foaming.MaterialTemp": encode_value("Real", 32.0),
        "DataBlocksGlobal.DB_Foaming.InjectionWeight": encode_value("Real", 850.0),
        "DataBlocksGlobal.DB_Foaming.InjectionPressure": encode_value("Real", 120.0),
        "DataBlocksGlobal.DB_Foaming.FixtureTemp": encode_value("Real", 45.0),
        "DataBlocksGlobal.DB_Foaming.CoreTemp": encode_value("Real", 48.0),
        "DataBlocksGlobal.DB_Foaming.CuringTime": encode_value("Real", 180.0),
        "DataBlocksGlobal.DB_Foaming.BoxBarcode": encode_value("String", "BX-B-0001", string_length=24),
        "DataBlocksGlobal.DB_Foaming.NGFlag": encode_value("Bool", False),
        "DataBlocksGlobal.DB_Interface.MaterialTempSetpoint": encode_value("Real", 32.0),
    }
    return MockPLCClient(tags)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S7CommPlus symbolic gateway CLI")
    parser.add_argument("--config", default="gateway/points.json")
    parser.add_argument("--mock", action="store_true", help="use the in-memory mock PLC")
    parser.add_argument("--read-all", action="store_true")
    parser.add_argument("--read", nargs="*", default=[])
    parser.add_argument("--write", nargs=2, metavar=("POINT", "VALUE"))
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--actor", default="cli")
    parser.add_argument("--poll", action="store_true")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--browse", action="store_true")
    args = parser.parse_args(argv)

    points = load_points(args.config)
    config = GatewayConfig.from_env(points)
    if args.mock:
        client = _mock_client()
        config.writes_enabled = True  # mock only; real PLC still needs the env flag
    else:
        client = S7CommPlusPLCClient(
            config.host, config.port, config.rack, config.slot,
            password=config.password, use_tls=config.use_tls,
        )
    gateway = Gateway(config, client, AuditLog())

    try:
        gateway.connect()
        if args.browse:
            print(json.dumps(gateway.browse(), ensure_ascii=False, indent=2))
        if args.read_all or args.read:
            values = gateway.read_points(args.read or None)
            print(json.dumps(values, ensure_ascii=False, indent=2, default=str))
        if args.write:
            name, raw_value = args.write
            point = next(p for p in points if p.name == name)
            value: object = raw_value
            if point.type in ("Real", "LReal"):
                value = float(raw_value)
            elif point.type in ("Int", "DInt", "Word", "UInt", "Byte", "USInt", "SInt"):
                value = int(raw_value)
            elif point.type == "Bool":
                value = raw_value.strip().lower() in ("1", "true", "yes", "on")
            print(json.dumps(
                gateway.write_point(name, value, approved=args.approved, actor=args.actor),
                ensure_ascii=False, indent=2, default=str))
        if args.poll:
            stop = threading.Event()
            for _ in range(args.cycles):
                print(json.dumps(gateway.poll_once(), ensure_ascii=False, default=str))
                time.sleep(config.poll_interval_s)
            stop.set()
    except (GatewayError, WriteRejected) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        gateway.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
