"""
Telegram diagnostics CLI (stdlib only).

Subcommands:
- getme                 Show bot identity
- send --chat <ID> --text "..."  Send test message
- updates [--limit N]   Print latest update ids + types
- ids                   Show env ids and validation

All calls print HTTP status and shortened JSON.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional
from urllib import request as _urlreq, parse as _urlparse


class _Resp:
    def __init__(self, status: int, text: str):
        self.status_code = int(status)
        self.text = text
        self.ok = 200 <= self.status_code < 300

    def json(self) -> Any:
        try:
            return json.loads(self.text or "{}")
        except Exception:
            return {"raw": self.text}


def _timeout() -> int:
    v = os.getenv("TELEGRAM_TIMEOUT_SEC", "25")
    try:
        return int(v)
    except Exception:
        return 25


def _debug() -> bool:
    return str(os.getenv("TELEGRAM_DEBUG", "")).strip().lower() in ("1", "true")


def _token() -> str | None:
    t = os.getenv("TELEGRAM_BOT_TOKEN")
    return t.strip() if t else None


def _base(tok: str) -> str:
    return f"https://api.telegram.org/bot{tok}/"


def _short(obj: Any, limit: int = 600) -> str:
    s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    return s[:limit] + ("…" if len(s) > limit else "")


def _get(url: str, params: Optional[dict] = None, timeout: int = 25) -> _Resp:
    if params:
        qs = _urlparse.urlencode(params)
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}{qs}"
    req = _urlreq.Request(url, method="GET")
    with _urlreq.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode("utf-8", errors="replace")
        return _Resp(getattr(r, "status", 200), txt)


def _post(url: str, payload: dict, timeout: int = 25) -> _Resp:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = _urlreq.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with _urlreq.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode("utf-8", errors="replace")
        return _Resp(getattr(r, "status", 200), txt)


def _print_status(resp: _Resp) -> None:
    print(f"HTTP {resp.status_code}")
    print(_short(resp.json(), 600))


class _HTTP:
    def get(self, url: str, params: dict | None = None, timeout: int = 25) -> _Resp:
        return _get(url, params=params, timeout=timeout)

    def post(self, url: str, json: dict | None = None, timeout: int = 25) -> _Resp:
        return _post(url, json or {}, timeout=timeout)


# Provide a monkeypatchable shim for tests
requests = _HTTP()


def cmd_getme() -> int:
    tok = _token()
    if not tok:
        print("error: missing TELEGRAM_BOT_TOKEN")
        return 2
    r = requests.get(f"{_base(tok)}getMe", timeout=_timeout())
    _print_status(r)
    if r.ok:
        try:
            res = r.json().get("result", {})
            print(f"username={res.get('username')} id={res.get('id')}")
        except Exception:
            pass
    return 0 if r.ok else 3


def cmd_send(chat: int, text: str) -> int:
    tok = _token()
    if not tok:
        print("error: missing TELEGRAM_BOT_TOKEN")
        return 2
    payload = {"chat_id": chat, "text": text}
    if _debug():
        print(f"-> sendMessage {_short(payload)}")
    r = requests.post(f"{_base(tok)}sendMessage", json=payload, timeout=_timeout())
    _print_status(r)
    return 0 if r.ok else r.status_code


def cmd_updates(limit: int = 3) -> int:
    tok = _token()
    if not tok:
        print("error: missing TELEGRAM_BOT_TOKEN")
        return 2
    r = requests.post(f"{_base(tok)}getUpdates", json={"timeout": 0, "limit": limit}, timeout=_timeout())
    if _debug():
        print(f"-> getUpdates {{'timeout':0,'limit':{limit}}}")
    _print_status(r)
    if not r.ok:
        return 4
    data = r.json()
    for it in data.get("result", []) or []:
        uid = it.get("update_id")
        typ = "callback" if it.get("callback_query") else ("message" if it.get("message") else "?")
        print(f"update {uid}: {typ}")
    return 0


def cmd_ids() -> int:
    tok = _token()
    cc_raw = os.getenv("TG_CHAT_CONTROL", "")
    al_raw = os.getenv("TG_ALLOWLIST", "")
    parsed, bad = [], []
    for s in [x.strip() for x in al_raw.split(",") if x.strip()]:
        try:
            parsed.append(int(s))
        except Exception:
            bad.append(s)
    print({
        "has_token": bool(tok),
        "chat_control": int(cc_raw) if cc_raw and cc_raw.lstrip("-").isdigit() else None,
        "allowlist": parsed,
        "bad_allowlist": bad,
    })
    return 0 if not bad else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tg_diag", add_help=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("getme")
    psend = sub.add_parser("send")
    psend.add_argument("--chat", type=int, required=True)
    psend.add_argument("--text", type=str, required=True)
    pupd = sub.add_parser("updates")
    pupd.add_argument("--limit", type=int, default=3)
    sub.add_parser("ids")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "getme":
        return cmd_getme()
    if args.cmd == "send":
        return cmd_send(args.chat, args.text)
    if args.cmd == "updates":
        return cmd_updates(args.limit)
    if args.cmd == "ids":
        return cmd_ids()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
