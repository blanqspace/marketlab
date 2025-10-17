from __future__ import annotations

# mypy: ignore-errors
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from marketlab.tui.db import ConnectionStatus, EventRow, HeaderData, OrderRow

if TYPE_CHECKING:
    class StaticBase:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def update(self, *args: Any, **kwargs: Any) -> None: ...

    class RichLogBase(StaticBase):
        def write(self, message: str) -> None: ...

        def clear(self) -> None: ...

else:  # pragma: no cover - runtime import only
    from textual.widgets import Static as StaticBase
    from textual.widgets import RichLog as RichLogBase


class HeaderBar(StaticBase):
    """Top status bar."""

    def show_message(self, message: str, *, style: str = "yellow") -> None:
        body = Text(message, justify="center", style=style)
        self.update(Panel(body, title="MarketLab Dashboard", border_style=style))

    def update_header(self, header: HeaderData) -> None:
        if isinstance(header.last_event_age, (int, float)):
            last_event_txt = f"{int(header.last_event_age)}s"
        else:
            last_event_txt = "n/a"
        body = Text.assemble(
            ("Mode: ", "bold"),
            (header.mode, "cyan"),
            "  |  ",
            ("State: ", "bold"),
            (header.state, "green" if header.state.lower() in {"run", "running"} else "yellow"),
            "  |  ",
            ("Uptime: ", "bold"),
            (header.uptime, "magenta"),
            "  |  ",
            ("Queue: ", "bold"),
            (str(header.queue_depth), "cyan"),
            "  |  ",
            ("Events/min: ", "bold"),
            (f"{header.events_per_min:.0f}", "cyan"),
            "  |  ",
            ("Last event: ", "bold"),
            (last_event_txt, "cyan"),
        )
        self.update(Panel(body, title="MarketLab Dashboard", border_style="cyan", padding=(0, 2)))


class KpiCard(StaticBase):
    def show_message(self, message: str, *, style: str = "yellow") -> None:
        self.update(Panel(Text(message, justify="center"), title="KPIs", border_style=style))

    def update_kpis(self, kpis: dict[str, Any]) -> None:
        table = Table(expand=True)
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        for key in ("queue_depth", "events_per_min", "last_event_age", "uptime"):
            value = kpis.get(key, "-")
            if key == "events_per_min" and isinstance(value, (int, float)):
                value = f"{value:.0f}"
            if key == "last_event_age" and isinstance(value, (int, float)) and value >= 0:
                value = f"{int(value)}s"
            table.add_row(key, str(value if value not in (None, "") else "-"))
        self.update(Panel(table, title="KPIs", border_style="blue"))


class ConnCard(StaticBase):
    def show_message(self, message: str, *, style: str = "yellow") -> None:
        self.update(Panel(Text(message, justify="center"), title="Connections", border_style=style))

    def update_connections(self, connections: Sequence[ConnectionStatus]) -> None:
        table = Table(expand=True)
        table.add_column("Service", style="bold", width=10)
        table.add_column("Status", width=10)
        table.add_column("Detail")
        table.add_column("Age", justify="right", width=6)

        if not connections:
            table.add_row("-", "-", "No connection data", "-")
        else:
            for entry in connections:
                color = {
                    "ok": "green",
                    "ready": "green",
                    "warn": "yellow",
                    "warning": "yellow",
                    "error": "red",
                    "info": "cyan",
                    "unknown": "grey50",
                }.get(entry.status, "cyan")
                if isinstance(entry.age_seconds, (int, float)):
                    age_txt = f"{int(entry.age_seconds)}s"
                else:
                    age_txt = "-"
                table.add_row(
                    entry.name,
                    f"[{color}]{entry.status}[/]",
                    entry.detail,
                    age_txt,
                )

        self.update(Panel(table, title="Connections", border_style="green"))


class OrdersTable(StaticBase):
    def show_message(self, message: str, *, style: str = "yellow") -> None:
        self.update(Panel(Text(message, justify="center"), title="Orders", border_style=style))

    def update_orders(self, orders: Sequence[OrderRow]) -> None:
        table = Table(expand=True)
        table.add_column("Token", width=10)
        table.add_column("Status", width=10)
        table.add_column("Age", justify="right", width=6)
        table.add_column("Sources")
        table.add_column("Event")

        if not orders:
            table.add_row("-", "-", "-", "-", "No order activity")
        else:
            for order in orders:
                if isinstance(order.age_seconds, (int, float)):
                    age_txt = f"{int(order.age_seconds)}s"
                else:
                    age_txt = "-"
                status_color = {
                    "pending": "yellow",
                    "confirmed": "green",
                    "rejected": "red",
                    "expired": "red",
                }.get(order.status, "cyan")
                table.add_row(
                    order.token,
                    f"[{status_color}]{order.status}[/]",
                    age_txt,
                    order.sources or "-",
                    order.message,
                )

        self.update(Panel(table, title="Orders (Top 20)", border_style="magenta"))


class EventsLog(RichLogBase):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            highlight=False,
            markup=True,
            wrap=True,
            max_lines=220,
            **kwargs,
        )

    def show_message(self, message: str, *, style: str = "yellow") -> None:
        self.clear()
        self.write(f"[{style}]{message}[/]")

    def set_events(self, events: Sequence[EventRow]) -> None:
        self.clear()
        for event in events:
            self.write(self._format_event(event))

    def append_events(self, events: Sequence[EventRow]) -> None:
        if not events:
            return
        for event in events:
            self.write(self._format_event(event))

    def _format_event(self, event: EventRow) -> str:
        lvl = event.level.lower()
        color = {
            "ok": "green",
            "info": "cyan",
            "warn": "yellow",
            "warning": "yellow",
            "error": "red",
        }.get(lvl, "white")
        ts = int(event.ts) if event.ts else 0
        age = max(0, int(time.time()) - ts) if ts else 0
        msg = event.message
        extra = ""
        if event.fields:
            try:
                pairs = []
                for key, value in event.fields.items():
                    if isinstance(value, (str, int, float)):
                        pairs.append(f"{key}={value}")
                if pairs:
                    extra = " " + ", ".join(pairs[:4])
            except Exception:
                extra = ""
        return f"[{color}]{lvl:<6}[/] {age:>4}s | {msg}{extra}"
