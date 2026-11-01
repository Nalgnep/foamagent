"""S7CommPlus symbolic gateway (route 2).

This package does NOT re-implement the S7CommPlus wire protocol.
It wraps the existing ``s7commplus`` library (lazy import, so tests and
the mock client work without it) and adds the layers a production
gateway actually needs:

* point table (symbolic names, types, access, limits)
* batch reads, type conversion, reconnect with backoff (reads only)
* write safety: whitelist, range, step, approval, audit, no write retry
* a mock PLC client so the whole gateway can be tested without a CPU

Real PLC use is read-only by default. Writes are disabled unless the
caller explicitly enables them AND the point is writable AND all
safety checks pass. See gateway/README.md.
"""

from .config import GatewayConfig, Point, load_config
from .gateway import Gateway, GatewayError, WriteRejected

__all__ = [
    "Gateway",
    "GatewayConfig",
    "GatewayError",
    "Point",
    "WriteRejected",
    "load_config",
]
