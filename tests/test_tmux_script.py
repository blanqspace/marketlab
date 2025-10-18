from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest


@pytest.mark.local
@pytest.mark.skipif(not sys.stdout.isatty(), reason="requires interactive TTY")
def test_tmux_launcher_attaches():
    if shutil.which("tmux") is None:
        pytest.skip("tmux not installed")
    script = Path(__file__).resolve().parents[1] / "tools" / "tmux_marketlab.sh"
    # Launching the full session is interactive; we only verify help output here.
    result = os.system(f"bash {script} --help >/dev/null")
    assert result == 0
