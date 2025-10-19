from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from src.marketlab.settings import get_settings
from src.marketlab.ipc import bus
from src.marketlab.utils.logging import get_logger
from src.marketlab.services.slack_transport import (
    ISlackTransport,
    MockSlackTransport,
    RealSlackTransport,
    SlackMessageRef,
)


class SlackBot:
    """Slack control channel companion for two-man approvals."""

    def __init__(self):
        settings = get_settings()
        self.enabled = bool(settings.SLACK_ENABLED)
        self.bot_token = settings.SLACK_BOT_TOKEN
        self.app_token = settings.SLACK_APP_TOKEN
        self.signing_secret = settings.SLACK_SIGNING_SECRET
        self.channel = settings.SLACK_CHANNEL_CONTROL
        self.post_as_thread = bool(settings.SLACK_POST_AS_THREAD)
        self.log = get_logger("slack")
        self.simulation = bool(settings.SLACK_SIMULATION)
        self.report_dir = settings.REPORT_DIR
        if self.simulation:
            self.web = None
            self.sock = None
        else:
            self.web = WebClient(token=self.bot_token) if self.bot_token else None
            self.sock = (
                SocketModeClient(app_token=self.app_token, web_client=self.web)
                if self.app_token and self.web
                else None
            )
        self.index_path = Path("runtime/slack/index.json")
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index = self._load_index()
        self._token_by_ts: dict[str, str] = {}
        for tok, entry in self._index.get("orders", {}).items():
            ts = entry.get("ts")
            if ts:
                self._token_by_ts[str(ts)] = tok
        self._seen_events: deque[str] = deque(maxlen=200)
        self._poll_interval = 3
        self._channel_id: Optional[str] = None
        self._running = False
        self.transport: ISlackTransport = self._create_transport()

    # --- index helpers ---
    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"orders": {}, "by_token": {}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"orders": {}, "by_token": {}}
            data.setdefault("orders", {})
            data.setdefault("by_token", {})
            return data
        except Exception as exc:
            self.log.warning("failed to load slack index", exc_info=exc)
            return {"orders": {}, "by_token": {}}

    def _save_index(self) -> None:
        with self._lock:
            payload = json.dumps(self._index, ensure_ascii=False, indent=2)
            self.index_path.write_text(payload, encoding="utf-8")

    def _create_transport(self) -> ISlackTransport:
        if self.simulation:
            return MockSlackTransport(report_dir=self.report_dir, log=self.log)
        if not self.web:
            raise RuntimeError("slack web client missing")
        return RealSlackTransport(
            web_client=self.web,
            channel=self.channel,
            post_as_thread=self.post_as_thread,
            log=self.log,
            call_with_retry=self._call_with_retry,
            channel_resolver=self._resolve_channel_id,
        )

    # --- posting helpers ---
    def _resolve_channel_id(self) -> Optional[str]:
        if self.simulation:
            self._channel_id = "SIM"
            return self._channel_id
        if self._channel_id:
            return self._channel_id
        if not self.web:
            return None
        channel = (self.channel or "").strip()
        if not channel:
            return None
        if channel.startswith("#"):
            target = channel.lstrip("#")
            cursor: Optional[str] = None
            while True:
                resp = self._call_with_retry(
                    self.web.conversations_list,
                    limit=1000,
                    cursor=cursor,
                    types="public_channel,private_channel",
                )
                channels = resp.get("channels", []) if resp else []
                for item in channels:
                    if item.get("name") == target or item.get("name_normalized") == target:
                        self._channel_id = item.get("id")
                        return self._channel_id
                cursor = resp.get("response_metadata", {}).get("next_cursor") if resp else None
                if not cursor:
                    break
            self.log.error("slack channel not found", extra={"channel": channel})
            return None
        self._channel_id = channel
        return self._channel_id

    def _call_with_retry(self, func, max_attempts: int = 5, **kwargs):
        attempt = 0
        backoff = 1.0
        while attempt < max_attempts:
            attempt += 1
            try:
                return func(**kwargs)
            except SlackApiError as exc:
                retry_after = 0
                if exc.response is not None and exc.response.headers:
                    retry_after = int(exc.response.headers.get("Retry-After", 0) or 0)
                self.log.warning(
                    "slack api error",
                    extra={
                        "attempt": attempt,
                        "api": getattr(func, "__name__", "unknown"),
                        "retry_after": retry_after,
                        "status": getattr(exc.response, "status_code", 0),
                    },
                )
                if retry_after:
                    time.sleep(retry_after + 1)
                    continue
                if getattr(exc.response, "status_code", 0) >= 500:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                raise
            except Exception as exc:
                self.log.error(
                    "slack call failed",
                    exc_info=exc,
                    extra={"attempt": attempt, "api": getattr(func, "__name__", "unknown")},
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
        raise RuntimeError("slack api retries exceeded")

    @staticmethod
    def _is_order_pending(evt: dict) -> bool:
        n = (evt.get("name") or evt.get("type") or evt.get("message") or "").lower()
        return any(
            key in n
            for key in [
                "orders.confirm.pending",
                "order.confirm.pending",
                "orders/confirm/pending",
                "order/confirm/pending",
                "confirm_pending",
            ]
        )

    @staticmethod
    def _is_order_ok(evt: dict, event: Optional[bus.Event] = None) -> bool:
        keys = [
            "orders.confirm.ok",
            "order.confirm.ok",
            "orders/confirm/ok",
            "order/confirm/ok",
            "confirm_ok",
        ]
        n = (evt.get("name") or evt.get("type") or evt.get("message") or "").lower()
        if any(key in n for key in keys):
            return True
        if event and event.message:
            msg = str(event.message).lower()
            return any(key in msg for key in keys)
        return False

    @staticmethod
    def _is_state_changed(evt: dict, event: Optional[bus.Event] = None) -> bool:
        keys = ["state.changed"]
        n = (evt.get("name") or evt.get("type") or evt.get("message") or "").lower()
        if any(key in n for key in keys):
            return True
        if event and event.message:
            msg = str(event.message).lower()
            return any(key in msg for key in keys)
        return False

    def _store_order_entry(
        self,
        token: str,
        ref: SlackMessageRef,
        *,
        status: str,
        sources: list[str],
        last_actor: Optional[str] = None,
        note: Optional[str] = None,
        confirmed_by: Optional[str] = None,
    ) -> None:
        with self._lock:
            orders = self._index.setdefault("orders", {})
            orders[token] = {
                "channel": ref.channel,
                "ts": ref.ts,
                "thread_ts": ref.thread_ts,
                "status": status,
                "sources": list(sources or []),
                "last_actor": last_actor,
                "note": note,
                "confirmed_by": confirmed_by,
                "updated_at": int(time.time()),
            }
            if ref.ts:
                self._token_by_ts[str(ref.ts)] = token
            self._index.setdefault("by_token", {})[token] = dict(ref.__dict__)
        self._save_index()

    def _order_entry(self, token: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._index.get("orders", {}).get(token, {}))

    def _make_ref_from_entry(self, entry: dict[str, Any]) -> Optional[SlackMessageRef]:
        if not entry or not entry.get("channel") or not entry.get("ts"):
            return None
        return SlackMessageRef(
            channel=str(entry["channel"]),
            ts=str(entry["ts"]),
            thread_ts=str(entry.get("thread_ts")) if entry.get("thread_ts") else None,
        )

    def post_order_pending(self, order: dict) -> SlackMessageRef:
        token = str(order.get("token") or "")
        if not token:
            raise RuntimeError("missing token for slack post")
        sources = list(order.get("sources") or [])
        note = order.get("note")
        last_actor = order.get("last_actor")
        ref = self.transport.post_order_pending(order)
        self._store_order_entry(
            token,
            ref,
            status="pending",
            sources=sources,
            last_actor=last_actor,
            note=note,
        )
        return ref

    def _update_order_pending(self, token: str, entry: dict[str, Any], note: Optional[str]) -> None:
        ref = self._make_ref_from_entry(entry)
        if not ref:
            return
        sources = entry.get("sources") or []
        order_payload = dict(entry)
        order_payload.setdefault("token", token)
        order_payload["sources"] = list(sources)
        if note is not None:
            order_payload["note"] = note
        try:
            self.transport.update_order_pending(ref, order_payload)
        except Exception as exc:
            self.log.error("failed to update pending order", exc_info=exc, extra={"token": token})
            return
        entry["note"] = note or entry.get("note")
        entry["updated_at"] = int(time.time())
        with self._lock:
            self._index.setdefault("orders", {})[token] = entry
        self._save_index()

    def update_order_confirmed(self, ref: SlackMessageRef, by_user: str) -> None:
        token = self._token_by_ts.get(str(ref.ts))
        entry = self._order_entry(token) if token else {}
        payload = dict(entry)
        if token:
            payload.setdefault("token", token)
        try:
            self.transport.update_order_confirmed(ref, by_user, payload)
        except Exception as exc:
            self.log.error("failed to update confirmed order", exc_info=exc, extra={"token": token})
            return
        if token:
            self._store_order_entry(
                token,
                SlackMessageRef(channel=ref.channel, ts=ref.ts, thread_ts=ref.thread_ts or ref.ts),
                status="confirmed",
                sources=list(payload.get("sources") or []),
                confirmed_by=by_user or payload.get("confirmed_by"),
            )
        self.log.info("slack order confirmed stored", extra={"token": token, "by": by_user})

    def post_state_change(self, state: str) -> None:
        self.log.info(f"post state: {state=}")
        try:
            self.transport.post_state(str(state))
        except Exception as exc:
            self.log.error("failed to mirror state change", exc_info=exc, extra={"state": state})

    # --- button -> enqueue ---
    def _handle_action(self, action: dict[str, Any], payload: dict[str, Any]) -> None:
        action_id = action.get("action_id")
        if not action_id:
            return
        value_raw = action.get("value") or "{}"
        try:
            parsed_value = json.loads(value_raw)
        except json.JSONDecodeError:
            parsed_value = {"value": value_raw}
        token = parsed_value.get("token")
        mapping: dict[str, tuple[str, dict[str, Any]]] = {
            "confirm_order": ("orders.confirm", {"token": token}),
            "reject_order": ("orders.reject", {"token": token}),
            "pause_state": ("state.pause", {}),
            "resume_state": ("state.resume", {}),
            "mode_paper": ("mode.switch", {"mode": "paper"}),
            "mode_live": ("mode.switch", {"mode": "live"}),
        }
        if action_id not in mapping:
            self.log.warning("unknown slack action", extra={"action_id": action_id})
            return
        cmd, args = mapping[action_id]
        if "token" in args and not token:
            self.log.warning("slack action missing token", extra={"action_id": action_id})
            return
        user = payload.get("user") or {}
        user_id = user.get("id")
        user_name = user.get("username") or user.get("name")
        actor = f"slack:{user_name or user_id or 'unknown'}"
        try:
            bus.enqueue(cmd, args, source="slack", actor_id=actor)
            bus.emit("info", "slack.action", action=action_id, token=token, by=actor)
        except Exception as exc:
            self.log.error(
                "failed to enqueue from slack",
                exc_info=exc,
                extra={"action_id": action_id, "cmd": cmd},
            )
            return
        if token:
            entry = self._order_entry(token)
            if not entry:
                self.log.warning("slack action without stored order", extra={"token": token})
            else:
                entry.setdefault("sources", [])
                if "slack" not in entry["sources"]:
                    entry["sources"].append("slack")
                entry["last_actor"] = actor
                ref = self._make_ref_from_entry(entry)
                if ref and self.post_as_thread:
                    try:
                        self._call_with_retry(
                            self.web.chat_postMessage,
                            channel=ref.channel,
                            thread_ts=ref.thread_ts or ref.ts,
                            text=f"🕒 Aktion {action_id} ausgelöst von {actor}",
                        )
                    except Exception:
                        pass
                with self._lock:
                    self._index.setdefault("orders", {})[token] = entry
                self._save_index()
        self.log.info("slack action enqueued", extra={"action_id": action_id, "cmd": cmd, "actor": actor})

    # --- socket mode lifecycle ---
    def _on_socket_event(self, req: SocketModeRequest):
        try:
            self.sock.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        except Exception as exc:
            self.log.warning("failed to ack slack request", exc_info=exc)
            return
        if req.type != "interactive":
            return
        payload = req.payload or {}
        if payload.get("type") != "block_actions":
            return
        for action in payload.get("actions", []):
            try:
                self._handle_action(action, payload)
            except Exception as exc:
                self.log.error("slack action handler failed", exc_info=exc)

    def start(self):
        if not self.enabled:
            self.log.warning("Slack disabled via settings")
            return
        if self._running:
            return
        if self.simulation:
            self._running = True
            threading.Thread(target=self._tail_events, daemon=True).start()
            self.log.info("Slack bot started", extra={"channel": "SIM", "mode": "simulation"})
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                self.log.info("Slack bot stopped via signal")
            return
        if not (self.web and self.sock):
            raise RuntimeError("Slack tokens not configured")
        channel_id = self._resolve_channel_id()
        if not channel_id:
            raise RuntimeError("Slack control channel missing")
        self._running = True
        self.sock.socket_mode_request_listeners.append(self._on_socket_event)
        self.sock.connect()
        threading.Thread(target=self._tail_events, daemon=True).start()
        self.log.info("Slack bot started", extra={"channel": channel_id})
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            self.log.info("Slack bot stopped via signal")

    def _event_key(self, event: bus.Event) -> str:
        fields = event.fields or {}
        return json.dumps({"ts": event.ts, "msg": event.message, "fields": fields}, sort_keys=True)

    def _tail_events(self):
        backoff = 1.0
        while self._running:
            try:
                events = bus.tail_events(limit=50)
                for event in reversed(events):
                    key = self._event_key(event)
                    if key in self._seen_events:
                        continue
                    self._seen_events.append(key)
                    evt = self._event_to_dict(event)
                    self.log.info(f"tail event: {evt['type']=} {evt.get('name')=} {evt.get('payload')=}")
                    self._dispatch_event(evt, event)
                backoff = 1.0
                time.sleep(self._poll_interval)
            except Exception as exc:
                self.log.error("tail error", exc_info=exc)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _event_to_dict(self, event: bus.Event) -> dict[str, Any]:
        payload = dict(event.fields or {})
        name = payload.get("name") or event.message
        type_name = payload.get("type") or name or event.message or ""
        return {
            "ts": event.ts,
            "level": event.level,
            "message": event.message,
            "type": type_name or "",
            "name": name or "",
            "payload": payload,
            "fields": dict(event.fields or {}),
        }

    def _dispatch_event(self, evt: dict[str, Any], event: bus.Event) -> None:
        fields = dict(evt.get("fields") or {})
        payload_raw = evt.get("payload")
        payload: dict[str, Any] = dict(fields)
        if isinstance(payload_raw, dict):
            payload.update(payload_raw)
        if self._is_order_pending(evt):
            order_source = payload_raw if isinstance(payload_raw, dict) else None
            if not order_source and fields:
                order_source = fields
            order = dict(order_source or {})
            if isinstance(order.get("order"), dict) and not order.get("token"):
                order = order["order"]
            token = order.get("token") or payload.get("token")
            if not token:
                return
            sources = order.get("sources") or payload.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            note = order.get("note") or payload.get("note")
            last_actor = order.get("last_actor") or payload.get("last_actor")
            entry = self._order_entry(token)
            if entry and entry.get("status") == "pending":
                entry["sources"] = list(sources or entry.get("sources") or [])
                if last_actor:
                    entry["last_actor"] = last_actor
                self._update_order_pending(token, entry, note)
                return
            if entry and entry.get("status") == "confirmed":
                # already confirmed; ignore duplicates
                return
            try:
                order_out = dict(order) if isinstance(order, dict) else {"token": token}
                order_out.setdefault("token", token)
                order_out.setdefault("sources", sources)
                if last_actor and not order_out.get("last_actor"):
                    order_out["last_actor"] = last_actor
                if note is not None and order_out.get("note") is None:
                    order_out["note"] = note
                ref = self.post_order_pending(order_out)
            except Exception as exc:
                self.log.error("failed to post pending order", exc_info=exc, extra={"token": token})
                return
        elif self._is_order_ok(evt, event):
            token = payload.get("token") or fields.get("token")
            if not token:
                return
            entry = self._order_entry(token)
            ref = self._make_ref_from_entry(entry)
            if not ref:
                self.log.warning("missing slack ref for confirmed order", extra={"token": token})
                return
            by_user = payload.get("by") or entry.get("last_actor")
            if not by_user:
                sources = payload.get("sources") or entry.get("sources") or []
                if isinstance(sources, str):
                    sources = [sources]
                by_user = ", ".join(sources) if sources else "unbekannt"
            self.update_order_confirmed(ref, str(by_user))
        elif self._is_state_changed(evt, event):
            state = payload.get("state") or fields.get("state")
            if not state:
                return
            self.post_state_change(str(state))


def run_forever():
    SlackBot().start()
