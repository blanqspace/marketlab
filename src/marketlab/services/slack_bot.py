from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class SlackMessageRef:
    channel: str
    ts: str
    thread_ts: Optional[str] = None


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
        self.web = WebClient(token=self.bot_token) if self.bot_token else None
        self.sock = (
            SocketModeClient(app_token=self.app_token, web_client=self.web)
            if self.app_token and self.web
            else None
        )
        self.log = get_logger("slack")
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

    # --- posting helpers ---
    def _resolve_channel_id(self) -> Optional[str]:
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

    def _build_order_blocks(
        self,
        token: str,
        sources: list[str],
        *,
        status: str,
        last_actor: Optional[str] = None,
        note: Optional[str] = None,
        confirmed_by: Optional[str] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        safe_sources = ", ".join(sources) if sources else "—"
        lines = [f"*Order* `{token}`"]
        if status == "pending":
            lines.append("⏳ Wartet auf Freigabe")
        else:
            lines.append(f"✅ Bestätigt ({confirmed_by or 'unbekannt'})")
        lines.append(f"Quellen: {safe_sources}")
        if last_actor:
            lines.append(f"Letzte Aktion: {last_actor}")
        if note:
            lines.append(f"Hinweis: {note}")
        text = "\n".join(lines)
        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            },
        ]
        if status == "pending":
            value = json.dumps({"token": token})
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "action_id": "confirm_order",
                            "text": {"type": "plain_text", "text": "✅ Bestätigen", "emoji": True},
                            "style": "primary",
                            "value": value,
                        },
                        {
                            "type": "button",
                            "action_id": "reject_order",
                            "text": {"type": "plain_text", "text": "❌ Ablehnen", "emoji": True},
                            "style": "danger",
                            "value": value,
                        },
                    ],
                }
            )
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "action_id": "pause_state",
                            "text": {"type": "plain_text", "text": "⏸ Pause", "emoji": True},
                            "value": "{}",
                        },
                        {
                            "type": "button",
                            "action_id": "resume_state",
                            "text": {"type": "plain_text", "text": "▶️ Resume", "emoji": True},
                            "value": "{}",
                        },
                        {
                            "type": "button",
                            "action_id": "mode_paper",
                            "text": {"type": "plain_text", "text": "📄 Paper", "emoji": True},
                            "value": json.dumps({"mode": "paper"}),
                        },
                        {
                            "type": "button",
                            "action_id": "mode_live",
                            "text": {"type": "plain_text", "text": "🟢 Live", "emoji": True},
                            "value": json.dumps({"mode": "live"}),
                        },
                    ],
                }
            )
        return text, blocks

    def post_order_pending(self, order: dict) -> SlackMessageRef:
        if not self.web:
            raise RuntimeError("slack web client missing")
        token = str(order.get("token") or "")
        sources = list(order.get("sources") or [])
        note = order.get("note")
        last_actor = order.get("last_actor")
        channel_id = self._resolve_channel_id()
        if not token or not channel_id:
            raise RuntimeError("missing token or channel for slack post")
        text, blocks = self._build_order_blocks(
            token,
            sources,
            status="pending",
            last_actor=last_actor,
            note=note,
        )
        response = self._call_with_retry(
            self.web.chat_postMessage,
            channel=channel_id,
            text=text,
            blocks=blocks,
        )
        ts = str(response["ts"])
        ref = SlackMessageRef(channel=str(response["channel"]), ts=ts)
        if self.post_as_thread:
            ref.thread_ts = ts
        self._store_order_entry(
            token,
            ref,
            status="pending",
            sources=sources,
            last_actor=last_actor,
            note=note,
        )
        self.log.info("slack order pending posted", extra={"token": token, "channel": ref.channel})
        return ref

    def _update_order_pending(self, token: str, entry: dict[str, Any], note: Optional[str]) -> None:
        if not self.web:
            return
        ref = self._make_ref_from_entry(entry)
        if not ref:
            return
        sources = entry.get("sources") or []
        last_actor = entry.get("last_actor")
        text, blocks = self._build_order_blocks(
            token,
            sources,
            status="pending",
            last_actor=last_actor,
            note=note or entry.get("note"),
        )
        self._call_with_retry(
            self.web.chat_update,
            channel=ref.channel,
            ts=ref.ts,
            text=text,
            blocks=blocks,
        )
        entry["note"] = note or entry.get("note")
        entry["updated_at"] = int(time.time())
        with self._lock:
            self._index.setdefault("orders", {})[token] = entry
        self._save_index()

    def update_order_confirmed(self, ref: SlackMessageRef, by_user: str) -> None:
        if not self.web:
            return
        token = self._token_by_ts.get(str(ref.ts))
        entry = self._order_entry(token) if token else {}
        sources = entry.get("sources") or []
        confirmed_by = by_user or entry.get("confirmed_by") or "n/a"
        text, blocks = self._build_order_blocks(
            token or "unbekannt",
            sources,
            status="confirmed",
            confirmed_by=confirmed_by,
            last_actor=entry.get("last_actor"),
            note=None,
        )
        self._call_with_retry(
            self.web.chat_update,
            channel=ref.channel,
            ts=ref.ts,
            text=text,
            blocks=blocks,
        )
        thread_ts = ref.thread_ts or ref.ts
        try:
            self._call_with_retry(
                self.web.chat_postMessage,
                channel=ref.channel,
                thread_ts=thread_ts,
                text=f"✅ Bestätigt von {confirmed_by}",
            )
        except Exception as exc:
            self.log.warning("failed to append confirmation thread", exc_info=exc)
        if token:
            self._store_order_entry(
                token,
                SlackMessageRef(channel=ref.channel, ts=ref.ts, thread_ts=thread_ts),
                status="confirmed",
                sources=sources,
                confirmed_by=confirmed_by,
            )
        self.log.info("slack order confirmed updated", extra={"token": token, "by": confirmed_by})

    def post_state_change(self, state: str) -> None:
        if not self.web:
            return
        channel_id = self._resolve_channel_id()
        if not channel_id:
            return
        self.log.info(f"post state: {state=}")
        text = f"ℹ️ State geändert → *{state.upper()}*"
        self._call_with_retry(
            self.web.chat_postMessage,
            channel=channel_id,
            text=text,
        )
        self.log.info("slack state message posted", extra={"state": state})

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
        if not (self.web and self.sock):
            raise RuntimeError("Slack tokens not configured")
        channel_id = self._resolve_channel_id()
        if not channel_id:
            raise RuntimeError("Slack control channel missing")
        if self._running:
            return
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
        name = (evt.get("name") or evt.get("type") or evt.get("message") or "").lower()
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
            entry = self._order_entry(token)
            if entry and entry.get("status") == "pending":
                entry["sources"] = list(sources or entry.get("sources") or [])
                self._update_order_pending(token, entry, note)
                return
            if entry and entry.get("status") == "confirmed":
                # already confirmed; ignore duplicates
                return
            try:
                order_out = dict(order) if isinstance(order, dict) else {"token": token}
                order_out.setdefault("token", token)
                order_out.setdefault("sources", sources)
                if note is not None:
                    order_out.setdefault("note", note)
                ref = self.post_order_pending(order_out)
            except Exception as exc:
                self.log.error("failed to post pending order", exc_info=exc, extra={"token": token})
                return
            with self._lock:
                by_token = self._index.setdefault("by_token", {})
                by_token[token] = dict(ref.__dict__)
            self._save_index()
        elif any(
            key in name
            for key in [
                "orders.confirm.ok",
                "order.confirm.ok",
                "orders/confirm/ok",
                "order/confirm/ok",
                "confirm_ok",
            ]
        ):
            token = payload.get("token")
            if not token:
                return
            entry = self._order_entry(token)
            ref = self._make_ref_from_entry(entry)
            if not ref:
                self.log.warning("missing slack ref for confirmed order", extra={"token": token})
                return
            sources = payload.get("sources") or []
            by_user = entry.get("last_actor")
            if not by_user:
                # fallback to list of sources
                by_user = ", ".join(sources) if sources else "unbekannt"
            try:
                self.update_order_confirmed(ref, by_user)
            except Exception as exc:
                self.log.error("failed to update confirmed order", exc_info=exc, extra={"token": token})
        elif "state.changed" in name or event.message == "state.changed":
            state = payload.get("state")
            if not state:
                return
            try:
                self.post_state_change(str(state))
            except Exception as exc:
                self.log.error("failed to mirror state change", exc_info=exc, extra={"state": state})
        elif event.message == "orders.confirm.ok":
            token = fields.get("token")
            if not token:
                return
            entry = self._order_entry(token)
            ref = self._make_ref_from_entry(entry)
            if not ref:
                self.log.warning("missing slack ref for confirmed order", extra={"token": token})
                return
            sources = fields.get("sources") or []
            by_user = entry.get("last_actor")
            if not by_user:
                # fallback to list of sources
                by_user = ", ".join(sources) if sources else "unbekannt"
            try:
                self.update_order_confirmed(ref, by_user)
            except Exception as exc:
                self.log.error("failed to update confirmed order", exc_info=exc, extra={"token": token})
        elif event.message == "state.changed":
            state = fields.get("state")
            if not state:
                return
            try:
                self.post_state_change(str(state))
            except Exception as exc:
                self.log.error("failed to mirror state change", exc_info=exc, extra={"state": state})


def run_forever():
    SlackBot().start()
