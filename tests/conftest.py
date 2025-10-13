import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_collection_modifyitems(config, items):
    if os.getenv("IBKR_LIVE") != "1":
        skip_live = pytest.mark.skip(reason="IBKR_LIVE=1 not set")
        for item in items:
            if "ibkr" in item.keywords:
                item.add_marker(skip_live)

    if os.getenv("PYTEST_NETWORK") != "1":
        skip_network = pytest.mark.skip(reason="PYTEST_NETWORK=1 not set")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)


@pytest.fixture
def mock_ibkr():
    class MockIBKR:
        def capabilities(self):
            return {"delayed": True, "realtime": False}

        def fetch_bars(self, symbol, timeframe, since=None, until=None):
            return [
                {
                    "ts": int(time.time()) - 60 * i,
                    "o": 1.0,
                    "h": 1.0,
                    "l": 1.0,
                    "c": 1.0,
                    "v": 0,
                }
                for i in range(50)
            ]

        async def subscribe_ticks(self, symbol):
            yield {"ts": int(time.time()), "bid": 1.0, "ask": 1.1}

    return MockIBKR()
