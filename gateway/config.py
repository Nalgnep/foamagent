"""Gateway configuration: point table and connection settings.

Passwords / certificates are NEVER stored in a point table or in git.
They come from environment variables at run time (see README.md).
Point ``symbol`` values must be replaced with the names returned by
``client.browse()`` on the real CPU; the bundled points.json uses
example symbolic paths for the Chengdu B-line foaming line.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    """One symbolic PLC variable exposed by the gateway."""

    name: str  # gateway-facing name, e.g. "material_ratio"
    symbol: str  # S7CommPlus symbolic name, e.g. "DataBlocksGlobal.DB_Foaming.MaterialRatio"
    type: str = "Real"  # Bool, Byte, USInt, SInt, Word, UInt, Int, DWord, UDInt, DInt, Real, LReal, String, Char
    unit: str = ""
    access: str = "read"  # "read" or "read_write"
    min_value: float | None = None
    max_value: float | None = None
    max_step: float | None = None  # max |new - last_read| for a write; None = no step check
    requires_approval: bool = False
    description: str = ""


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 102
    rack: int = 0
    slot: int = 1
    use_tls: bool | str = "auto"  # True / False / "auto" (passed to s7commplus)
    password: str | None = None
    timeout_s: float = 5.0
    max_retries: int = 3  # reads only; writes are never retried
    backoff_s: float = 0.5
    batch_size: int = 50
    poll_interval_s: float = 1.0
    writes_enabled: bool = False
    points: list[Point] = field(default_factory=list)

    @classmethod
    def from_env(cls, points: list[Point]) -> "GatewayConfig":
        """Build a config from environment variables (no secrets in files)."""

        def _bool(name: str, default: bool) -> bool:
            return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

        use_tls_raw = os.environ.get("S7_USE_TLS", "auto").strip().lower()
        use_tls: bool | str = "auto" if use_tls_raw == "auto" else use_tls_raw in ("1", "true", "yes", "on")
        return cls(
            host=os.environ.get("S7_HOST", "127.0.0.1"),
            port=int(os.environ.get("S7_PORT", "102")),
            rack=int(os.environ.get("S7_RACK", "0")),
            slot=int(os.environ.get("S7_SLOT", "1")),
            use_tls=use_tls,
            password=os.environ.get("S7_PASSWORD") or None,
            writes_enabled=_bool("GATEWAY_WRITES_ENABLED", False),
            points=points,
        )


def load_points(path: str) -> list[Point]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    points = []
    for item in data if isinstance(data, list) else data.get("points", []):
        points.append(Point(**{k: v for k, v in item.items() if k in Point.__dataclass_fields__}))
    names = [p.name for p in points]
    if len(names) != len(set(names)):
        raise ValueError("duplicate point names in point table")
    symbols = [p.symbol for p in points]
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate point symbols in point table")
    return points


def load_config(path: str) -> GatewayConfig:
    """Load a JSON file of the form {"points": [...], ...overrides}."""

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    points = load_points(path) if isinstance(data, list) else [
        Point(**{k: v for k, v in item.items() if k in Point.__dataclass_fields__})
        for item in data.get("points", [])
    ]
    overrides = {k: v for k, v in data.items() if k in GatewayConfig.__dataclass_fields__ and k != "points"} if isinstance(data, dict) else {}
    return GatewayConfig(points=points, **overrides)
