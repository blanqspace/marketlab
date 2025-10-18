# ruff: noqa
import os
import time
import json
import re
from typing import Any, Optional

from marketlab.net.http import SafeHttpClient

from marketlab.core.control_policy import risk_of_command
from marketlab.services.telegram_usecases import build_main_menu, enqueue_control, handle_callback
from marketlab.ipc import bus
from marketlab.core.timefmt import iso_utc
from marketlab.bootstrap.env import load_env


class _HTTPResponse:
    """Minimal response wrapper to mimic requests.Response using stdlib."""

    def __init__(self, status_code: int, text: str):
        self.status_code = int(status_code)
        self.text = text
        self.ok = 200 <= self.status_code < 300

    def json(self) -> Any:
        return json.loads(self.text or "{}")


class _HTTP:
    def __init__(self):
        self._client = SafeHttpClient({"api.telegram.org"})

    def get(self, url: str, params: Optional[dict] = None, timeout: int = 5) -> _HTTPResponse:
        response = self._client.get(url, params=params or None, timeout=float(timeout))
        return _HTTPResponse(response.status_code, response.text)

    def post(self, url: str, json: Optional[dict] = None, timeout: int = 5) -> _HTTPResponse:
        data = json or {}
        response = self._client.post(
            url,
            json=data,
            timeout=float(timeout),
            headers={"Content-Type": "application/json"},
        )
        return _HTTPResponse(response.status_code, response.text)


def _short(obj: Any, limit: int = 600) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:limit] + ("…" if len(s) > limit else "")


requests = _HTTP()  # exposed for tests to monkeypatch

PIN_SESSION_TTL = 60


def _action_to_cmd(action: str) -> str:
    mapping = {
        "pause": "state.pause",
        "resume": "state.resume",
        "stop": "stop.now",
        "confirm": "orders.confirm",
        "confirm_token": "orders.confirm",
        "reject": "orders.reject",
        "reject_token": "orders.reject",
        "mode_paper": "mode.switch",
        "mode_live": "mode.switch",
    }
    return mapping.get(action, "")


def _requires_pin(cmd: str, pin: str) -> bool:
    if not pin or not cmd:
        return False
    return risk_of_command(cmd) in ("HIGH", "CRITICAL")


def _pin_session_ok(pin_cache: dict[int, float], actor_id: int | None) -> bool:
    if actor_id is None:
        return False
    expiry = pin_cache.get(int(actor_id))
    if not expiry:
        return False
    if time.time() > expiry:
        pin_cache.pop(int(actor_id), None)
        return False
    return True


def _set_pin_session(pin_cache: dict[int, float], actor_id: int | None) -> None:
    if actor_id is None:
        return
    pin_cache[int(actor_id)] = time.time() + PIN_SESSION_TTL


def _allow_rate(rate_tracker: dict[int, list[float]], actor_id: int | None, limit: int) -> bool:
    if not limit or actor_id is None:
        return True
    now = time.time()
    bucket = rate_tracker.setdefault(int(actor_id), [])
    bucket[:] = [ts for ts in bucket if now - ts < 60]
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _validate_env_from_settings() -> tuple[dict, list[str]]:
    """Build and validate Telegram config from Settings()."""
    s = load_env(mirror=True)  # ensure .env loaded and legacy keys mirrored
    t = s.telegram
    cfg: dict[str, Any] = {}
    errs: list[str] = []
    token: str = (t.bot_token.get_secret_value() if t.bot_token else "").strip()
    if not token:
        errs.append("TELEGRAM_BOT_TOKEN missing")
    if token and not re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", token):
        errs.append("TELEGRAM_BOT_TOKEN format invalid (expected <digits>:<secret>)")
    cfg["token"] = token

    chat = t.chat_control
    if chat is None:
        errs.append("TG_CHAT_CONTROL missing")
    else:
        try:
            chat = int(chat)
        except Exception:
            errs.append("TG_CHAT_CONTROL must be integer (negative for groups)")
            chat = None
    cfg["chat"] = chat

    allow: set[int] = set(int(x) for x in (t.allowlist or []) if str(x).strip())
    cfg["allow"] = allow
    cfg["timeout"] = int(t.timeout_sec)
    try:
        cfg["long_poll"] = int(getattr(t, "long_poll_sec", t.timeout_sec))
    except Exception:
        cfg["long_poll"] = int(t.timeout_sec)
    cfg["debug"] = bool(t.debug)
    cfg["enabled"] = bool(t.enabled)
    cfg["mock"] = bool(t.mock)
    pin = getattr(t, "command_pin", None)
    cfg["pin"] = str(pin).strip() if pin else ""
    try:
        cfg["rate_limit"] = int(getattr(t, "rate_limit_per_min", 10))
    except Exception:
        cfg["rate_limit"] = 10
    # Publish state for dashboard panels
    try:
        bus.set_state("tg.enabled", "1" if t.enabled else "0")
        bus.set_state("tg.mock", "1" if t.mock else "0")
        if chat is not None:
            bus.set_state("tg.chat_control", str(int(chat)))
        bus.set_state("tg.allowlist_count", str(len(allow)))
    except Exception:
        pass
    return cfg, errs


def _base_url(token: str) -> str:
    # Important: include trailing slash
    return f"https://api.telegram.org/bot{token}/"


def _log_http(
    debug: bool, prefix: str, url: str, payload: Any | None, resp: _HTTPResponse | None
) -> None:
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
    cfg, errs = _validate_env_from_settings()
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
    rate_limit: int = int(cfg.get("rate_limit", 10))
    pin_code: str = str(cfg.get("pin") or "")
    pin_cache: dict[int, float] = {}
    rate_tracker: dict[int, list[float]] = {}
    base = _base_url(token)

    if mock:
        print("mock-mode: no network; poller idle")
        try:
            bus.set_state("tg.last_ok_ts", iso_utc())
        except Exception:
            pass
        if once:
            return 0
        sleep_sec = max(1, int(cfg.get("long_poll", timeout)))
        try:
            while True:
                time.sleep(float(sleep_sec))
        except KeyboardInterrupt:  # pragma: no cover - interactive stop
            return 0

    http = requests

    # Startup checks and banner (mock writes files instead)
    msg_url = f"{base}sendMessage"

    def rate_allowed(sender: int | None, chat_id: int, cb_id: str | None = None) -> bool:
        if _allow_rate(rate_tracker, sender, rate_limit):
            return True
        text = "Rate limit erreicht. Bitte kurz warten."
        if cb_id:
            requests.post(
                f"{base}answerCallbackQuery",
                json={"callback_query_id": cb_id, "text": text},
                timeout=timeout,
            )
        requests.post(
            msg_url,
            json={"chat_id": chat_id, "text": text},
            timeout=timeout,
        )
        return False

    def pin_allowed(cmd: str, sender: int | None, chat_id: int, cb_id: str | None = None) -> bool:
        if not _requires_pin(cmd, pin_code):
            return True
        if _pin_session_ok(pin_cache, sender):
            return True
        hint = "PIN erforderlich. Sende /pin <PIN>"
        if cb_id:
            requests.post(
                f"{base}answerCallbackQuery",
                json={"callback_query_id": cb_id, "text": hint},
                timeout=timeout,
            )
        requests.post(
            msg_url,
            json={"chat_id": chat_id, "text": hint},
            timeout=timeout,
        )
        return False
    if not mock:
        url = f"{base}getMe"
        _log_http(debug, "-> GET", url, None, None)
        try:
            me = http.get(url, timeout=timeout)
        except Exception:
            print("ERROR: getMe failed; invalid token or network")
            try:
                bus.set_state("tg.last_err", "getMe exception")
                bus.emit("error", "tg.error", stage="getMe", status=-1)
            except Exception:
                pass
            return 3
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
        resp = http.post(msg_url, json=payload, timeout=timeout)
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
        print("mock-mode: no network; waiting for events")

    offset: Optional[int] = None

    while True:
        if mock:
            time.sleep(1.0)
            if once:
                return 0
            continue
        try:
            lp = max(5, int(cfg.get("long_poll", timeout)))
            upd_body: dict[str, Any] = {"timeout": lp}
            if offset is not None:
                upd_body["offset"] = offset
            upd_url = f"{base}getUpdates"
            _log_http(debug, "-> POST", upd_url, upd_body, None)
            r = http.post(upd_url, json=upd_body, timeout=timeout)
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
                        requests.post(
                            f"{base}answerCallbackQuery",
                            json={"callback_query_id": cb_id, "text": "Fehler: Zugriff verweigert"},
                            timeout=timeout,
                        )
                        continue
                    if not rate_allowed(sender_id, chat, cb_id):
                        continue
                    cmd_name = _action_to_cmd(str(parsed.get("action", "")))
                    if not pin_allowed(cmd_name, sender_id, chat, cb_id):
                        continue
                    try:
                        handle_callback(parsed, actor_id=sender_id)
                        requests.post(
                            f"{base}answerCallbackQuery",
                            json={
                                "callback_query_id": cb_id,
                                "text": f"OK: {parsed.get('action')}",
                            },
                            timeout=timeout,
                        )
                        try:
                            requests.post(
                                msg_url,
                                json={
                                    "chat_id": chat,
                                    "text": "MarketLab Control",
                                    "reply_markup": build_main_menu(),
                                },
                                timeout=timeout,
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        requests.post(
                            f"{base}answerCallbackQuery",
                            json={"callback_query_id": cb_id, "text": f"Fehler: {e}"},
                            timeout=timeout,
                        )
                        try:
                            if str(e).startswith("Bitte ID"):
                                requests.post(
                                    msg_url,
                                    json={
                                        "chat_id": chat,
                                        "text": "Bitte ID angeben: /confirm <ID> oder /reject <ID>",
                                    },
                                    timeout=timeout,
                                )
                        except Exception:
                            pass
                    continue

                # Text commands
                msg = upd.get("message")
                if msg and isinstance(msg.get("text"), str):
                    chat_id = msg.get("chat", {}).get("id", chat)
                    if allow and (sender_id not in allow):
                        requests.post(
                            msg_url,
                            json={"chat_id": chat_id, "text": "Fehler: Zugriff verweigert"},
                            timeout=timeout,
                        )
                        continue
                    txt = msg["text"].strip()
                    if txt.startswith("/pin"):
                        if not pin_code:
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "PIN nicht aktiviert"},
                                timeout=timeout,
                            )
                        else:
                            parts = txt.split(maxsplit=1)
                            provided = parts[1].strip() if len(parts) > 1 else ""
                            if provided == pin_code:
                                _set_pin_session(pin_cache, sender_id)
                                requests.post(
                                    msg_url,
                                    json={
                                        "chat_id": chat_id,
                                        "text": f"PIN ok ({PIN_SESSION_TTL}s)",
                                    },
                                    timeout=timeout,
                                )
                            else:
                                requests.post(
                                    msg_url,
                                    json={"chat_id": chat_id, "text": "PIN falsch"},
                                    timeout=timeout,
                                )
                        continue
                    if not rate_allowed(sender_id, chat_id):
                        continue
                    try:
                        if txt == "/pause":
                            if not pin_allowed("state.pause", sender_id, chat_id):
                                continue
                            enqueue_control("state.pause", {}, sender_id)
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "OK: pause"},
                                timeout=timeout,
                            )
                        elif txt == "/resume":
                            if not pin_allowed("state.resume", sender_id, chat_id):
                                continue
                            enqueue_control("state.resume", {}, sender_id)
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "OK: resume"},
                                timeout=timeout,
                            )
                        elif txt == "/paper":
                            if not pin_allowed("mode.switch", sender_id, chat_id):
                                continue
                            enqueue_control(
                                "mode.switch",
                                {
                                    "target": "paper",
                                    "args": {"symbols": ["AAPL"], "timeframe": "1m"},
                                },
                                sender_id,
                            )
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "OK: mode.paper"},
                                timeout=timeout,
                            )
                        elif txt == "/live":
                            if not pin_allowed("mode.switch", sender_id, chat_id):
                                continue
                            enqueue_control(
                                "mode.switch",
                                {
                                    "target": "live",
                                    "args": {"symbols": ["AAPL"], "timeframe": "1m"},
                                },
                                sender_id,
                            )
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "OK: mode.live"},
                                timeout=timeout,
                            )
                        elif txt.startswith("/confirm "):
                            tok = txt.split(maxsplit=1)[1].strip()
                            if tok:
                                if not pin_allowed("orders.confirm", sender_id, chat_id):
                                    continue
                                enqueue_control("orders.confirm", {"token": tok}, sender_id)
                                requests.post(
                                    msg_url,
                                    json={"chat_id": chat_id, "text": f"OK: confirm {tok}"},
                                    timeout=timeout,
                                )
                            else:
                                requests.post(
                                    msg_url,
                                    json={
                                        "chat_id": chat_id,
                                        "text": "Bitte Token angeben: /confirm <TOKEN>",
                                    },
                                    timeout=timeout,
                                )
                        elif txt.startswith("/reject "):
                            tok = txt.split(maxsplit=1)[1].strip()
                            if tok:
                                if not pin_allowed("orders.reject", sender_id, chat_id):
                                    continue
                                enqueue_control("orders.reject", {"token": tok}, sender_id)
                                requests.post(
                                    msg_url,
                                    json={"chat_id": chat_id, "text": f"OK: reject {tok}"},
                                    timeout=timeout,
                                )
                            else:
                                requests.post(
                                    msg_url,
                                    json={
                                        "chat_id": chat_id,
                                        "text": "Bitte Token angeben: /reject <TOKEN>",
                                    },
                                    timeout=timeout,
                                )
                        elif txt in ("/stop", "/stopnow"):
                            enqueue_control("stop.now", {}, sender_id)
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "OK: stop.now"},
                                timeout=timeout,
                            )
                        elif txt in ("/stop", "/stopnow"):
                            if not pin_allowed("stop.now", sender_id, chat_id):
                                continue
                            enqueue_control("stop.now", {}, sender_id)
                            requests.post(
                                msg_url,
                                json={"chat_id": chat_id, "text": "OK: stop.now"},
                                timeout=timeout,
                            )
                    except Exception as e:
                        requests.post(
                            msg_url,
                            json={"chat_id": chat_id, "text": f"Fehler: {e}"},
                            timeout=timeout,
                        )
            time.sleep(1)
        except Exception:
            time.sleep(2)


if __name__ == "__main__":
    ONCE = os.getenv("TG_POLLER_ONCE", "0").strip().lower() in ("1", "true")
    raise SystemExit(main(once=ONCE))
