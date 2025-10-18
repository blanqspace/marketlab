from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.local
def test_tmux_script_help():
    if not sys.stdout.isatty():
        pytest.skip("requires TTY")
    if shutil.which("tmux") is None:
        pytest.skip("tmux not available")
    script = Path(__file__).resolve().parents[1] / "tools" / "tmux_marketlab.sh"
    result = subprocess.run([str(script), "--help"], check=False, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Usage" in result.stdout
