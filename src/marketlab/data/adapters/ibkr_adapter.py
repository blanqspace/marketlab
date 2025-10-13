from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable
from importlib import import_module

from marketlab.ipc import bus


def _load_ib_class():
    module = import_module("ib_insync")
    return getattr(module, "IB")


@dataclass
class _ConnectionState:
    host: str
    port: int
    client_id: int


class IBKRAdapter:
    """Lightweight IBKR adapter used for tests and offline workflows."""

    def __init__(self) -> None:
        self._ib = None
        self._state: _ConnectionState | None = None

    def connect(self, host: str, port: int, *, client_id: int, timeout_sec: int) -> "IBKRAdapter":
        ib_class = _load_ib_class()
        self._ib = ib_class()
        self._ib.connect(host, port, clientId=client_id, timeout=timeout_sec)
        try:
            self._ib.reqMarketDataType(3)
        except Exception:
            # Some simulators do not support reqMarketDataType; ignore.
            pass
        self._state = _ConnectionState(host, port, client_id)
        bus.set_state("ibkr.connected", "1")
        bus.set_state("ibkr.client_id", str(client_id))
        return self

    def disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:
                pass
        self._ib = None
        bus.set_state("ibkr.connected", "0")

    def capabilities(self) -> dict[str, Any]:
        return {"delayed": True, "realtime": False}

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        since: int | None = None,
        until: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        now = int(time.time())
        return [
            {
                "ts": now - 60 * idx,
                "o": 1.0,
                "h": 1.0,
                "l": 1.0,
                "c": 1.0,
                "v": 0,
            }
            for idx in range(10)
        ]

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield {"ts": int(time.time()), "bid": 1.0, "ask": 1.1, "symbol": symbol}
            await asyncio.sleep(1)
