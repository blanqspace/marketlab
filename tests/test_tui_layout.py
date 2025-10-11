from __future__ import annotations
import io
import sys

from tools.tui_dashboard import render


def test_render_no_print_and_screen_false():
    # capture stdout around render()
    old = sys.stdout
    buf = io.StringIO()
    try:
        sys.stdout = buf
        r = render()
    finally:
        sys.stdout = old
    assert r is not None
    # ensure render() did not print to stdout
    assert buf.getvalue() == ""

