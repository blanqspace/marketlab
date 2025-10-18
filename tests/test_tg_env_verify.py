from __future__ import annotations

import os

import pytest

from tools.verify_telegram_env import verify_telegram_env


def test_verify_telegram_env_errors(monkeypatch, capsys):
    for key in [
        "TELEGRAM_ENABLED",
        "TELEGRAM_MOCK",
        "TELEGRAM_BOT_TOKEN",
        "TG_CHAT_CONTROL",
        "TG_ALLOWLIST",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    rc = verify_telegram_env()
    captured = capsys.readouterr().out
    assert rc == 2
    assert "TELEGRAM_BOT_TOKEN missing" in captured


def test_verify_telegram_env_ok(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_MOCK", "0")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCDEFGHIJKLMNOPQRSTUVWX")
    monkeypatch.setenv("TG_CHAT_CONTROL", "-100200")
    monkeypatch.setenv("TG_ALLOWLIST", "1,2")
    rc = verify_telegram_env()
    assert rc == 0
    assert "OK: Telegram environment looks valid" in capsys.readouterr().out
