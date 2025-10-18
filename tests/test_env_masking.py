from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_env_check_masks_token(tmp_path, monkeypatch):
    proj = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": f"{proj / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}",
            "TELEGRAM_ENABLED": "1",
            "TELEGRAM_MOCK": "0",
            "TELEGRAM_BOT_TOKEN": "123456789:supersecrettokenvalue",
            "TG_CHAT_CONTROL": "-1001",
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/env_check.py"],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    out = result.stdout
    assert "123456789:****" in out
    assert "supersecrettokenvalue" not in out
