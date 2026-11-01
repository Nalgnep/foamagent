"""PLC client abstraction.

Two implementations:

* :class:`S7CommPlusPLCClient` -- wraps the real ``s7commplus``
  library. Imported lazily, so importing this module never requires
  that package. It uses symbolic names only (``read_tags`` /
  ``write_tags``); it never computes an absolute DB offset, which is
  exactly why it works with optimized blocks.
* :class:`MockPLCClient` -- in-memory tags for tests and for running
  the gateway without a CPU. It can be told to fail the next N
  reads/writes so reconnect / no-retry behaviour is testable.

Writes through the real client are deliberately single-attempt:
``s7commplus`` itself never retries writes, because after a
transport failure the caller cannot know whether the PLC already
applied the write. The gateway preserves that rule.
"""

from __future__ import annotations

import time
from typing import Protocol


class PLCError(Exception):
    """Transport / protocol error from the PLC side."""


class PLCClient(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    @property
    def connected(self) -> bool: ...
    def read_tags(self, names: list[str]) -> dict[str, bytes]: ...
    def write_tags(self, values: dict[str, bytes]) -> None: ...
    def browse(self) -> list[dict]: ...


class S7CommPlusPLCClient:
    """Real client. Requires ``pip install s7commplus``."""

    def __init__(self, host: str, port: int = 102, rack: int = 0, slot: int = 1,
                 password: str | None = None, use_tls=False, timeout_s: float = 5.0):
        self.host, self.port, self.rack, self.slot = host, port, rack, slot
        self.password, self.use_tls, self.timeout_s = password, use_tls, timeout_s
        self._client = None

    def connect(self) -> None:
        try:
            from s7commplus.client import S7CommPlusClient
        except ImportError as exc:  # pragma: no cover - exercised only on real PLC
            raise PLCError(
                "s7commplus is not installed; run: pip install s7commplus==0.3.0"
            ) from exc
        client = S7CommPlusClient()
        try:
            client.connect(
                self.host, port=self.port, rack=self.rack, slot=self.slot,
                password=self.password, use_tls=self.use_tls,
            )
        except Exception as exc:
            raise PLCError(f"failed to connect to {self.host}:{self.port}: {exc}") from exc
        self._client = client

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            finally:
                self._client = None

    @property
    def connected(self) -> bool:
        return self._client is not None and bool(getattr(self._client, "connected", True))

    def _require(self):
        if self._client is None:
            raise PLCError("not connected")
        return self._client

    def read_tags(self, names: list[str]) -> dict[str, bytes]:
        client = self._require()
        try:
            results = client.read_tags(list(names))
        except Exception as exc:
            raise PLCError(f"read_tags failed: {exc}") from exc
        out: dict[str, bytes] = {}
        for result in results:
            if result.error is not None:
                raise PLCError(f"read failed for {result.tag}: {result.error}")
            if result.value is None:
                raise PLCError(f"read returned no value for {result.tag}")
            out[result.tag.name if hasattr(result.tag, "name") else str(result.tag)] = result.value
        # s7commplus returns results in request order; map back by name.
        # TagResult.tag is a SymbolicTag; its string form contains the name,
        # so fall back to request order when the name key is not usable.
        if set(out) != set(names):
            out = {name: r.value for name, r in zip(names, results) if r.value is not None}
        return out

    def write_tags(self, values: dict[str, bytes]) -> None:
        client = self._require()
        try:
            results = client.write_tags(dict(values))
        except Exception as exc:
            raise PLCError(f"write_tags failed (state unknown, not retried): {exc}") from exc
        for result in results:
            if result.error is not None:
                raise PLCError(f"write failed for {result.tag}: {result.error}")

    def browse(self) -> list[dict]:
        client = self._require()
        try:
            return list(client.browse())
        except Exception as exc:
            raise PLCError(f"browse failed: {exc}") from exc


class MockPLCClient:
    """In-memory PLC for tests. Values are raw bytes per tag name."""

    def __init__(self, tags: dict[str, bytes] | None = None):
        self.tags: dict[str, bytes] = dict(tags or {})
        self._connected = False
        self.connect_calls = 0
        self.read_calls = 0
        self.write_calls = 0
        self.fail_reads = 0  # fail the next N read_tags calls, then succeed
        self.fail_writes = 0

    def connect(self) -> None:
        self._connected = True
        self.connect_calls += 1

    def disconnect(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def read_tags(self, names: list[str]) -> dict[str, bytes]:
        if not self._connected:
            raise PLCError("not connected")
        self.read_calls += 1
        if self.fail_reads > 0:
            self.fail_reads -= 1
            raise PLCError("simulated link failure on read")
        missing = [n for n in names if n not in self.tags]
        if missing:
            raise PLCError(f"unknown tags: {missing}")
        return {n: self.tags[n] for n in names}

    def write_tags(self, values: dict[str, bytes]) -> None:
        if not self._connected:
            raise PLCError("not connected")
        self.write_calls += 1
        if self.fail_writes > 0:
            self.fail_writes -= 1
            raise PLCError("simulated link failure on write")
        self.tags.update(values)

    def browse(self) -> list[dict]:
        return [{"name": name} for name in sorted(self.tags)]


def connect_with_backoff(client: PLCClient, max_retries: int, backoff_s: float,
                         sleep=time.sleep) -> None:
    """Connect, retrying only before any request has been sent.

    Used for reads and for the initial connect before a write.
    It is NOT used to retry a write that may already have been sent.
    """
    last: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            client.connect()
            return
        except Exception as exc:  # noqa: BLE001 - backoff loop, error is re-raised
            last = exc
            if attempt < max_retries:
                sleep(backoff_s * (2**attempt))
    assert last is not None
    raise PLCError(f"could not connect after {max_retries + 1} attempts: {last}")
