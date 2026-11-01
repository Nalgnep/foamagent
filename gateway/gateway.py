"""Gateway: point table + batching + safety + audit, on top of a PLC client.

Safety order for a write (all must pass, in this order):
1. gateway writes enabled (config)
2. point exists and is read_write
3. type-valid value
4. range check (min/max, numeric points only)
5. step check (|new - last read| <= max_step, when a last read exists)
6. approval (requires_approval points need approved=True on the call)
7. single write attempt, never retried; transport failure -> audit
   entry with status "unknown" (the PLC may or may not have applied it)

Reads are retried with backoff on link failure. Writes are not:
a retried write can apply twice or apply to a stale variable.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone

from .client import PLCClient, PLCError, connect_with_backoff
from .config import GatewayConfig, Point
from .types import decode_value, encode_value, validate_type


class GatewayError(Exception):
    pass


class WriteRejected(GatewayError):
    """A write that failed a safety check and was NOT sent to the PLC."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Append-only audit log. JSON Lines; no update/delete API by design."""

    def __init__(self, path: str | None = None):
        self.path = path
        self.entries: list[dict] = []
        self._lock = threading.Lock()

    def record(self, **fields) -> dict:
        entry = {"ts": _now_iso(), **fields}
        with self._lock:
            self.entries.append(entry)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry


class Gateway:
    def __init__(self, config: GatewayConfig, client: PLCClient, audit: AuditLog | None = None):
        self.config = config
        self.client = client
        self.audit = audit or AuditLog()
        self._points: dict[str, Point] = {}
        for point in config.points:
            validate_type(point.type)
            if point.name in self._points:
                raise ValueError(f"duplicate point {point.name}")
            self._points[point.name] = point
        self._last_read: dict[str, object] = {}
        self._lock = threading.Lock()

    # -- discovery -----------------------------------------------------
    def points(self) -> list[dict]:
        return [asdict(p) for p in self._points.values()]

    def browse(self) -> list[dict]:
        return self.client.browse()

    # -- connection ----------------------------------------------------
    def connect(self) -> None:
        connect_with_backoff(self.client, self.config.max_retries, self.config.backoff_s)
        self.audit.record(event="connect", host=self.config.host, port=self.config.port)

    def disconnect(self) -> None:
        self.client.disconnect()
        self.audit.record(event="disconnect")

    def _ensure_connected(self) -> None:
        if not self.client.connected:
            self.connect()

    # -- reads ---------------------------------------------------------
    def read_points(self, names: list[str] | None = None) -> dict[str, object]:
        """Batch-read points, chunked to config.batch_size.

        Reads are retried on link failure (with backoff) because a read
        has no side effect. Unknown names raise GatewayError and are
        not silently dropped.
        """
        wanted = list(names) if names is not None else list(self._points)
        unknown = [n for n in wanted if n not in self._points]
        if unknown:
            raise GatewayError(f"unknown points: {unknown}")
        result: dict[str, object] = {}
        for i in range(0, len(wanted), max(1, self.config.batch_size)):
            chunk = wanted[i : i + self.config.batch_size]
            symbols = [self._points[n].symbol for n in chunk]
            raw = self._read_raw_with_retry(symbols)
            for name, symbol in zip(chunk, symbols):
                point = self._points[name]
                value = decode_value(point.type, raw[symbol])
                result[name] = value
                self._last_read[name] = value
        self.audit.record(event="read", points=wanted, ok=True)
        return result

    def _read_raw_with_retry(self, symbols: list[str]) -> dict[str, bytes]:
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                self._ensure_connected()
                return self.client.read_tags(symbols)
            except Exception as exc:  # noqa: BLE001 - retry loop, re-raised below
                last = exc
                # Force a fresh connection for the next attempt.
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                if attempt < self.config.max_retries:
                    time.sleep(self.config.backoff_s * (2**attempt))
        assert last is not None
        self.audit.record(event="read", points=symbols, ok=False, error=str(last))
        raise GatewayError(f"read failed after retries: {last}") from last

    # -- writes --------------------------------------------------------
    def write_point(self, name: str, value, *, approved: bool = False, actor: str = "gateway") -> dict:
        """Write one point after all safety checks. Single attempt only."""
        with self._lock:
            point = self._points.get(name)
            if point is None:
                raise WriteRejected(f"unknown point {name}")
            if not self.config.writes_enabled:
                raise WriteRejected("gateway writes are disabled (GATEWAY_WRITES_ENABLED)")
            if point.access != "read_write":
                raise WriteRejected(f"point {name} is read-only")
            try:
                raw = encode_value(point.type, value)
            except Exception as exc:
                raise WriteRejected(f"invalid value for {name} ({point.type}): {exc}") from exc
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if point.min_value is not None and value < point.min_value:
                    raise WriteRejected(f"{name}={value} below min {point.min_value}")
                if point.max_value is not None and value > point.max_value:
                    raise WriteRejected(f"{name}={value} above max {point.max_value}")
                if point.max_step is not None and name in self._last_read:
                    last = self._last_read[name]
                    if isinstance(last, (int, float)) and abs(value - last) > point.max_step:
                        raise WriteRejected(
                            f"{name} step {abs(value - last)} exceeds max_step {point.max_step} "
                            f"(last read {last}, new {value})"
                        )
            if point.requires_approval and not approved:
                raise WriteRejected(f"{name} requires approval (approved=True)")
            # Safety checks passed. Connect if needed (before any send),
            # then exactly one write attempt, never retried.
            try:
                self._ensure_connected()
                self.client.write_tags({point.symbol: raw})
            except Exception as exc:  # noqa: BLE001 - state after failure is unknown
                self.audit.record(event="write", point=name, value=value, actor=actor,
                                  ok=False, status="unknown",
                                  error=f"transport failure, PLC state unknown, not retried: {exc}")
                raise GatewayError(f"write to {name} failed, PLC state unknown, not retried: {exc}") from exc
            self._last_read[name] = value
            entry = self.audit.record(event="write", point=name, value=value, actor=actor, ok=True)
            return {"point": name, "value": value, "audit_ts": entry["ts"]}

    # -- polling -------------------------------------------------------
    def poll_once(self) -> dict[str, object]:
        return self.read_points()

    def start_polling(self, callback, stop_event: threading.Event) -> threading.Thread:
        """Poll in a background thread; callback(values) on each cycle."""

        def _loop() -> None:
            while not stop_event.is_set():
                try:
                    callback(self.read_points())
                except Exception as exc:  # noqa: BLE001 - poller must survive a bad cycle
                    self.audit.record(event="poll_error", ok=False, error=str(exc))
                stop_event.wait(self.config.poll_interval_s)

        thread = threading.Thread(target=_loop, daemon=True, name="gateway-poller")
        thread.start()
        return thread
