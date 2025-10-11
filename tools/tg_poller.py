import os
import time
import json
import re
from typing import Any, Optional
from urllib import request as _urlreq, parse as _urlparse

from src.marketlab.services.telegram_usecases import build_main_menu, handle_callback
from src.marketlab.ipc import bus
from src.marketlab.core.timefmt import iso_utc


class _HTTPResponse:
    """Minimal response wrapper to mimic requests.Response using stdlib."""

    def __init__(self, status_code: int, text: str):
        self.status_code = int(status_code)
        self.text = text
        self.ok = 200 <= self.status_code < 300

    def json(self) -> Any:
        return json.loads(self.text or "{}")


class _HTTP:
    def get(self, url: str, params: Optional[dict] = None, timeout: int = 5) -> _HTTPResponse:
        if params:
            qs = _urlparse.urlencode(params)
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}{qs}"
        req = _urlreq.Request(url, method="GET")
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return _HTTPResponse(getattr(resp, "status", 200), body)

    def post(self, url: str, json: Optional[dict] = None, timeout: int = 5) -> _HTTPResponse:
        data = (json or {})
        payload = json_dump(data)
        req = _urlreq.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return _HTTPResponse(getattr(resp, "status", 200), body)


def json_dump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _short(obj: Any, limit: int = 600) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:limit] + ("…" if len(s) > limit else "")


requests = _HTTP()  # exposed for tests to monkeypatch


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _validate_env() -> tuple[dict, list[str]]:
    """Validate required TELEGRAM_* env and return cfg + errors."""
    cfg: dict[str, Any] = {}
    errs: list[str] = []
    try:
        token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    except KeyError:
        token = ""
        errs.append("TELEGRAM_BOT_TOKEN missing")
    if token and not re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", token):
        errs.append("TELEGRAM_BOT_TOKEN format invalid (expected <digits>:<secret>)")
    cfg["token"] = token

    chat_raw = os.getenv("TG_CHAT_CONTROL", "").strip()
    if not chat_raw:
        errs.append("TG_CHAT_CONTROL missing")
        chat = None
    else:
        try:
            chat = int(chat_raw)
        except Exception:
            chat = None
            errs.append("TG_CHAT_CONTROL must be integer (negative for groups)")
    cfg["chat"] = chat

    allow_raw = os.getenv("TG_ALLOWLIST", "").strip()
    allow: set[int] = set()
    if allow_raw:
        bad: list[str] = []
        for part in allow_raw.split(","):
            s = part.strip()
            if not s:
                continue
            try:
                allow.add(int(s))
            except Exception:
                bad.append(s)
        if bad:
            errs.append("TG_ALLOWLIST contains non-integers: " + ", ".join(bad))
    cfg["allow"] = allow

    cfg["timeout"] = int(os.getenv("TELEGRAM_TIMEOUT_SEC", "25") or 25)
    cfg["debug"] = _env_bool("TELEGRAM_DEBUG", False)
    cfg["enabled"] = _env_bool("TELEGRAM_ENABLED", False)
    cfg["mock"] = _env_bool("TELEGRAM_MOCK", False)
    return cfg, errs


def _base_url(token: str) -> str:
    # Important: include trailing slash
    return f"https://api.telegram.org/bot{token}/"


def _log_http(debug: bool, prefix: str, url: str, payload: Any | None, resp: _HTTPResponse | None) -> None:
    if not debug:
        return
    if payload is None:
        print(f"{prefix} {url}")
    else:
        print(f"{prefix} {url} {_short(payload)}")
    if resp is not None:
        try:
            print(f"<- {resp.status_code} {_short(resp.json())}")
        except Exception:
            print(f"<- {resp.status_code} {_short(resp.text)}")


def main(once: bool = False) -> int:
    cfg, errs = _validate_env()
    if errs:
        print("ERROR: Telegram environment invalid")
        for e in errs:
            print(f"- {e}")
        return 2
    if not cfg.get("enabled"):
        print("telegram disabled; set TELEGRAM_ENABLED=1 to start")
        return 0

    token: str = cfg["token"]
    chat: int = cfg["chat"]  # type: ignore[assignment]
    timeout: int = int(cfg["timeout"])  # type: ignore[arg-type]
    debug: bool = bool(cfg["debug"])  # type: ignore[arg-type]
    allow: set[int] = cfg["allow"]  # type: ignore[assignment]
    mock: bool = bool(cfg.get("mock", False))
    base = _base_url(token)

    # Startup checks and banner (mock writes files instead)
    msg_url = f"{base}sendMessage"
    if not mock:
        url = f"{base}getMe"
        _log_http(debug, "-> GET", url, None, None)
        me = requests.get(url, timeout=timeout)
        _log_http(debug, "", url, None, me)
        if not me.ok:
            print("ERROR: getMe failed; invalid token or network")
            try:
                bus.set_state("tg.last_err", "getMe failed")
                bus.emit("error", "tg.error", stage="getMe", status=me.status_code)
            except Exception:
                pass
            return 3
        try:
            data = me.json().get("result", {})
            print(f"getMe ok: {data.get('username')} (id={data.get('id')})")
            try:
                bus.set_state("tg.bot_username", str(data.get("username") or ""))
                bus.set_state("tg.last_ok_ts", iso_utc())
            except Exception:
                pass
        except Exception:
            print("getMe ok")

        banner = "?? MarketLab Bot ready"
        payload = {"chat_id": chat, "text": banner, "reply_markup": build_main_menu()}
        _log_http(debug, "-> POST", msg_url, payload, None)
        resp = requests.post(msg_url, json=payload, timeout=timeout)
        _log_http(debug, "", msg_url, None, resp)
        if resp.status_code in (400, 403):
            txt = resp.text.lower()
            if "chat not found" in txt:
                print("ERROR: Chat not found - check TG_CHAT_CONTROL and bot in chat")
            elif "blocked by the user" in txt:
                print("ERROR: bot blocked - un-block the bot in chat/user")
            elif "rights" in txt or "not enough" in txt:
                print("ERROR: missing rights - ensure bot is admin for group actions")
            else:
                print(f"ERROR: telegram returned {resp.status_code}: {_short(resp.text)}")
            try:
                bus.set_state("tg.last_err", f"{resp.status_code}")
                bus.emit("error", "tg.error", stage="banner", status=resp.status_code)
            except Exception:
                pass
        else:
            try:
                bus.set_state("tg.last_ok_ts", iso_utc())
            except Exception:
                pass
    else:
        # Mock: write banner into runtime/telegram_mock
        try:
            import pathlib
            d = pathlib.Path("runtime/telegram_mock")
            d.mkdir(parents=True, exist_ok=True)
            (d / "sendMessage_start.json").write_text(json.dumps({"chat_id": chat, "text": "?? MarketLab Bot ready"}, ensure_ascii=False, indent=2), encoding="utf-8")
            print("getMe ok: mock-mode")
            try:
                bus.set_state("tg.last_ok_ts", iso_utc())
            except Exception:
                pass
        except Exception:
            pass

    offset: Optional[int] = None
    if once:
        return 0

    while True:
        try:
            upd_body: dict[str, Any] = {"timeout": 20}
            if offset is not None:
                upd_body["offset"] = offset
            upd_url = f"{base}getUpdates"
            _log_http(debug, "-> POST", upd_url, upd_body, None)
            r = requests.post(upd_url, json=upd_body, timeout=timeout)
            _log_http(debug, "", upd_url, None, r)
            if not r.ok:
                time.sleep(2)
                continue
            data = r.json()
            for upd in data.get("result", []) or []:
                offset = int(upd.get("update_id", 0)) + 1

                # Identify sender (for allowlist)
                sender_id: Optional[int] = None
                if upd.get("callback_query"):
                    sender_id = upd["callback_query"].get("from", {}).get("id")
                elif upd.get("message"):
                    sender_id = upd["message"].get("from", {}).get("id")

                # Handle callback
                cb = upd.get("callback_query")
                if cb:
                    data_raw = cb.get("data")
                    cb_id = cb.get("id")
                    if not data_raw:
                        continue
                    # Parse data
                    parsed = None
                    try:
                        parsed = json.loads(data_raw)
                    except Exception:
                        if isinstance(data_raw, str) and data_raw.startswith("ORD:CONFIRM:"):
                            oid = data_raw.split(":")[2]
                            parsed = {"action": "confirm", "id": oid}
                        elif isinstance(data_raw, str) and data_raw.startswith("ORD:REJECT:"):
                            oid = data_raw.split(":")[2]
                            parsed = {"action": "reject", "id": oid}
                    if not parsed:
                        continue
                    if allow and (sender_id not in allow):
                        requests.post(f"{base}answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Fehler: Zugriff verweigert"}, timeout=timeout)
                        continue
                    try:
                        handle_callback(parsed)
                        requests.post(f"{base}answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"OK: {parsed.get('action')}"}, timeout=timeout)
                        try:
                            requests.post(msg_url, json={"chat_id": chat, "text": "MarketLab Control", "reply_markup": build_main_menu()}, timeout=timeout)
                        except Exception:
                            pass
                    except Exception as e:
                        requests.post(f"{base}answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"Fehler: {e}"}, timeout=timeout)
                        try:
                            if str(e).startswith("Bitte ID"):
                                requests.post(msg_url, json={"chat_id": chat, "text": "Bitte ID angeben: /confirm <ID> oder /reject <ID>"}, timeout=timeout)
                        except Exception:
                            pass
                    continue

                # Text commands
                msg = upd.get("message")
                if msg and isinstance(msg.get("text"), str):
                    chat_id = msg.get("chat", {}).get("id", chat)
                    if allow and (sender_id not in allow):
                        requests.post(msg_url, json={"chat_id": chat_id, "text": "Fehler: Zugriff verweigert"}, timeout=timeout)
                        continue
                    txt = msg["text"].strip()
                    try:
                        if txt == "/pause":
                            bus.enqueue("state.pause", {}, source="telegram")
                            requests.post(msg_url, json={"chat_id": chat_id, "text": "OK: pause"}, timeout=timeout)
                        elif txt == "/resume":
                            bus.enqueue("state.resume", {}, source="telegram")
                            requests.post(msg_url, json={"chat_id": chat_id, "text": "OK: resume"}, timeout=timeout)
                        elif txt == "/paper":
                            bus.enqueue("mode.switch", {"target": "paper", "args": {"symbols": ["AAPL"], "timeframe": "1m"}}, source="telegram")
                            requests.post(msg_url, json={"chat_id": chat_id, "text": "OK: mode.paper"}, timeout=timeout)
                        elif txt == "/live":
                            bus.enqueue("mode.switch", {"target": "live", "args": {"symbols": ["AAPL"], "timeframe": "1m"}}, source="telegram")
                            requests.post(msg_url, json={"chat_id": chat_id, "text": "OK: mode.live"}, timeout=timeout)
                        elif txt.startswith("/confirm "):
                            tok = txt.split(maxsplit=1)[1].strip()
                            if tok:
                                bus.enqueue("orders.confirm", {"token": tok}, source="telegram")
                                requests.post(msg_url, json={"chat_id": chat_id, "text": f"OK: confirm {tok}"}, timeout=timeout)
                            else:
                                requests.post(msg_url, json={"chat_id": chat_id, "text": "Bitte Token angeben: /confirm <TOKEN>"}, timeout=timeout)
                        elif txt.startswith("/reject "):
                            tok = txt.split(maxsplit=1)[1].strip()
                            if tok:
                                bus.enqueue("orders.reject", {"token": tok}, source="telegram")
                                requests.post(msg_url, json={"chat_id": chat_id, "text": f"OK: reject {tok}"}, timeout=timeout)
                            else:
                                requests.post(msg_url, json={"chat_id": chat_id, "text": "Bitte Token angeben: /reject <TOKEN>"}, timeout=timeout)
                    except Exception as e:
                        requests.post(msg_url, json={"chat_id": chat_id, "text": f"Fehler: {e}"}, timeout=timeout)
            time.sleep(1)
        except Exception:
            time.sleep(2)


if __name__ == "__main__":
    ONCE = os.getenv("TG_POLLER_ONCE", "0").strip().lower() in ("1", "true")
    raise SystemExit(main(once=ONCE))
