from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SlackMessageRef:
    channel: str
    ts: str
    thread_ts: Optional[str] = None


class ISlackTransport:
    def post_order_pending(self, order: Dict[str, Any]) -> SlackMessageRef:
        raise NotImplementedError

    def update_order_pending(self, ref: SlackMessageRef, order: Dict[str, Any]) -> None:
        raise NotImplementedError

    def update_order_confirmed(
        self,
        ref: SlackMessageRef,
        by_user: str,
        order: Optional[Dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError

    def post_state(self, state: str) -> None:
        raise NotImplementedError


class RealSlackTransport(ISlackTransport):
    def __init__(
        self,
        *,
        web_client,
        channel: str,
        post_as_thread: bool,
        log,
        call_with_retry: Optional[Callable[..., Any]] = None,
        channel_resolver: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.web = web_client
        self.channel = channel
        self.post_as_thread = post_as_thread
        self.log = log
        self._channel_resolver = channel_resolver
        self._channel_id: Optional[str] = None
        if call_with_retry is None:
            self._call_with_retry = lambda func, **kwargs: func(**kwargs)
        else:
            self._call_with_retry = call_with_retry

    def _resolve_channel(self) -> str:
        if self._channel_id:
            return self._channel_id
        resolved = None
        if self._channel_resolver:
            try:
                resolved = self._channel_resolver()
            except Exception as exc:
                if self.log:
                    self.log.warning("failed to resolve slack channel", exc_info=exc)
        channel = resolved or self.channel
        if not channel:
            raise RuntimeError("slack control channel missing")
        self._channel_id = channel
        return channel

    @staticmethod
    def _normalize_sources(sources: Any) -> List[str]:
        if not sources:
            return []
        if isinstance(sources, str):
            return [sources]
        try:
            return [str(src) for src in sources if str(src).strip()]
        except Exception:
            return [str(sources)]

    def _build_order_blocks(
        self,
        *,
        token: str,
        sources: List[str],
        status: str,
        last_actor: Optional[str] = None,
        note: Optional[str] = None,
        confirmed_by: Optional[str] = None,
    ) -> tuple[str, List[Dict[str, Any]]]:
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
        blocks: List[Dict[str, Any]] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            }
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

    def post_order_pending(self, order: Dict[str, Any]) -> SlackMessageRef:
        channel = self._resolve_channel()
        token = str(order.get("token") or "")
        if not token:
            raise RuntimeError("missing token for slack post")
        sources = self._normalize_sources(order.get("sources"))
        last_actor = order.get("last_actor")
        note = order.get("note")
        text, blocks = self._build_order_blocks(
            token=token,
            sources=sources,
            status="pending",
            last_actor=last_actor,
            note=note,
        )
        response = self._call_with_retry(
            self.web.chat_postMessage,
            channel=channel,
            text=text,
            blocks=blocks,
        )
        ts = str(response["ts"])
        ref = SlackMessageRef(
            channel=str(response.get("channel") or channel),
            ts=ts,
            thread_ts=ts if self.post_as_thread else None,
        )
        if self.log:
            self.log.info("slack order pending posted", extra={"token": token, "channel": ref.channel})
        return ref

    def update_order_pending(self, ref: SlackMessageRef, order: Dict[str, Any]) -> None:
        token = str(order.get("token") or "")
        sources = self._normalize_sources(order.get("sources"))
        last_actor = order.get("last_actor")
        note = order.get("note")
        text, blocks = self._build_order_blocks(
            token=token or "unbekannt",
            sources=sources,
            status="pending",
            last_actor=last_actor,
            note=note,
        )
        self._call_with_retry(
            self.web.chat_update,
            channel=ref.channel,
            ts=ref.ts,
            text=text,
            blocks=blocks,
        )

    def update_order_confirmed(
        self,
        ref: SlackMessageRef,
        by_user: str,
        order: Optional[Dict[str, Any]] = None,
    ) -> None:
        order = order or {}
        token = str(order.get("token") or "unbekannt")
        sources = self._normalize_sources(order.get("sources"))
        last_actor = order.get("last_actor")
        confirmed_by = by_user or order.get("confirmed_by") or "n/a"
        text, blocks = self._build_order_blocks(
            token=token,
            sources=sources,
            status="confirmed",
            confirmed_by=confirmed_by,
            last_actor=last_actor,
        )
        self._call_with_retry(
            self.web.chat_update,
            channel=ref.channel,
            ts=ref.ts,
            text=text,
            blocks=blocks,
        )
        if self.post_as_thread:
            thread_ts = ref.thread_ts or ref.ts
            try:
                self._call_with_retry(
                    self.web.chat_postMessage,
                    channel=ref.channel,
                    thread_ts=thread_ts,
                    text=f"✅ Bestätigt von {confirmed_by}",
                )
            except Exception as exc:
                if self.log:
                    self.log.warning("failed to append confirmation thread", exc_info=exc)
        if self.log:
            self.log.info("slack order confirmed updated", extra={"token": token, "by": confirmed_by})

    def post_state(self, state: str) -> None:
        channel = self._resolve_channel()
        text = f"ℹ️ State geändert → *{state.upper()}*"
        self._call_with_retry(
            self.web.chat_postMessage,
            channel=channel,
            text=text,
        )
        if self.log:
            self.log.info("slack state message posted", extra={"state": state})


class MockSlackTransport(ISlackTransport):
    """Schreibt alle Posts/Updates in runtime/reports/slack_sim.jsonl und simuliert Erfolg."""

    def __init__(self, report_dir: str = "runtime/reports", log=None):
        self.report_dir = report_dir
        os.makedirs(report_dir, exist_ok=True)
        self.path = os.path.join(report_dir, "slack_sim.jsonl")
        self.log = log

    def _write(self, record: Dict[str, Any]) -> None:
        record["t"] = time.time()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def post_order_pending(self, order: Dict[str, Any]) -> SlackMessageRef:
        now = time.time()
        ref = SlackMessageRef(channel="SIM", ts=str(now), thread_ts=str(now))
        self._write({"type": "post_pending", "order": order, "ref": ref.__dict__})
        if self.log:
            self.log.info("sim order pending posted", extra={"token": order.get("token")})
        return ref

    def update_order_pending(self, ref: SlackMessageRef, order: Dict[str, Any]) -> None:
        self._write({"type": "update_pending", "order": order, "ref": ref.__dict__})

    def update_order_confirmed(
        self,
        ref: SlackMessageRef,
        by_user: str,
        order: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._write({"type": "update_ok", "ref": ref.__dict__, "by": by_user, "order": order or {}})
        if self.log:
            self.log.info("sim order confirmed updated", extra={"ref": ref.ts, "by": by_user})

    def post_state(self, state: str) -> None:
        self._write({"type": "post_state", "state": state})
        if self.log:
            self.log.info("sim state message posted", extra={"state": state})
