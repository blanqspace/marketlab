from __future__ import annotations

from rich.console import Console
from src.marketlab.supervisor import build_menu_panel


def test_menu_render_message(tmp_path):
    db = str(tmp_path / "ctl.db")
    panel = build_menu_panel(db, None, None, message="OK: state.resume")
    console = Console(width=80, record=True)
    console.print(panel)
    txt = console.export_text()
    assert "OK: state.resume" in txt

