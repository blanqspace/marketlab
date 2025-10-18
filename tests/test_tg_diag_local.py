from __future__ import annotations

import types
from typing import Any

import importlib
import json
import pytest


class _Resp:
    def __init__(self, status: int, body: Any):
        self.status_code = status
        self._body = body
        self.ok = 200 <= status < 300
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_getme_ok(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abcxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    import tools.tg_diag as diag

    importlib.reload(diag)

    def fake_get(url, **kw):
        assert url.endswith("/getMe")
        return _Resp(200, {"ok": True, "result": {"id": 42, "is_bot": True, "username": "ml"}})

    monkeypatch.setattr(diag.requests, "get", fake_get)
    assert diag.cmd_getme() == 0


def test_getme_fail(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abcxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    import tools.tg_diag as diag

    importlib.reload(diag)

    def fake_get(url, **kw):
        return _Resp(401, {"ok": False, "description": "unauthorized"})

    monkeypatch.setattr(diag.requests, "get", fake_get)
    assert diag.cmd_getme() != 0


def test_send_variants(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abcxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    import tools.tg_diag as diag

    importlib.reload(diag)

    def fake_post(url, json=None, **kw):
        if json and json.get("text") == "ping":
            return _Resp(200, {"ok": True})
        return _Resp(403, {"ok": False, "description": "Forbidden: bot was blocked by the user"})

    monkeypatch.setattr(diag.requests, "post", fake_post)
    assert diag.cmd_send(-100123, "ping") == 0
    rc = diag.cmd_send(-100123, "other")
    assert rc == 403


def test_updates_parse(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abcxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    import tools.tg_diag as diag

    importlib.reload(diag)

    body = {
        "ok": True,
        "result": [
            {"update_id": 1, "message": {"from": {"id": 7}}},
            {"update_id": 2, "callback_query": {"from": {"id": 8}}},
        ],
    }

    def fake_post(url, json=None, **kw):
        return _Resp(200, body)

    monkeypatch.setattr(diag.requests, "post", fake_post)
    assert diag.cmd_updates(2) == 0
