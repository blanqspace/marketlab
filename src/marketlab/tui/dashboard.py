from __future__ import annotations

# mypy: ignore-errors
from collections.abc import Sequence

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.reactive import reactive
from textual.worker import WorkerFailed

from marketlab.bootstrap.env import load_env
from marketlab.settings import get_settings
from marketlab.tui.db import (
    DatabaseUnavailableError,
    EventBatch,
    EventRow,
    Snapshot,
    read_snapshot,
    stream_new_events,
)
from marketlab.tui.widgets import ConnCard, EventsLog, HeaderBar, KpiCard, OrdersTable

MAX_EVENT_BUFFER = 200


class DashboardApp(App[None]):
    """Read-only Textual dashboard."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #grid {
        padding: 1 2;
        grid-gutter: 1 1;
        grid-columns: 1fr 1fr;
        grid-rows: auto 1fr 2fr;
    }
    #header {
        column-span: 2;
    }
    #events {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Reload snapshot"),
    ]

    db_path: reactive[str | None] = reactive(None)

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        self.db_path = db_path
        self._header = HeaderBar(id="header")
        self._kpi = KpiCard(id="kpis")
        self._conn = ConnCard(id="connections")
        self._orders = OrdersTable(id="orders")
        self._events = EventsLog(id="events")
        self._last_event_id = 0
        self._events_buffer: list[EventRow] = []
        self._needs_snapshot = True
        self._resolved_db_path: str | None = None

    def resolve_db_path(self) -> str | None:
        if self._resolved_db_path is None:
            load_env(mirror=True)
            self._resolved_db_path = get_settings().ipc_db
        return self._resolved_db_path

    def compose(self) -> ComposeResult:
        yield Grid(
            self._header,
            self._kpi,
            self._conn,
            self._orders,
            self._events,
            id="grid",
        )

    async def on_mount(self) -> None:
        if not self.db_path:
            self.db_path = self.resolve_db_path()
        await self._refresh_snapshot()
        self.set_interval(1.0, self._tick)

    async def _tick(self) -> None:
        if self._needs_snapshot:
            await self._refresh_snapshot()
        else:
            await self._stream_events()

    async def _refresh_snapshot(self) -> None:
        db_path = self.db_path or self.resolve_db_path()
        if not db_path:
            self._show_waiting("waiting for DB path")
            return
        try:
            worker = self.run_worker(
                lambda: read_snapshot(db_path),
                thread=True,
                exit_on_error=False,
            )
            snapshot: Snapshot = await worker.wait()
        except WorkerFailed as worker_exc:
            error = worker_exc.error
            if isinstance(error, DatabaseUnavailableError):
                self._show_waiting("waiting for DB")
                self._needs_snapshot = True
                return
            self._show_error(str(error))
            self._needs_snapshot = True
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._show_error(str(exc))
            self._needs_snapshot = True
            return

        self._apply_snapshot(snapshot)
        self._needs_snapshot = False

    async def _stream_events(self) -> None:
        db_path = self.db_path or self.resolve_db_path()
        if not db_path:
            self._show_waiting("waiting for DB path")
            return
        try:
            worker = self.run_worker(
                lambda: stream_new_events(db_path, self._last_event_id),
                thread=True,
                exit_on_error=False,
            )
            batch: EventBatch = await worker.wait()
        except WorkerFailed as worker_exc:
            error = worker_exc.error
            if isinstance(error, DatabaseUnavailableError):
                self._show_waiting("waiting for DB")
                self._needs_snapshot = True
                return
            # retry with full snapshot next tick for all other errors
            self._needs_snapshot = True
            return
        except Exception:
            # retry with full snapshot next tick
            self._needs_snapshot = True
            return

        if not batch.events:
            return
        self._last_event_id = batch.last_event_id
        self._append_events(batch.events)

    def _apply_snapshot(self, snapshot: Snapshot) -> None:
        self._last_event_id = snapshot.last_event_id
        self._events_buffer = list(snapshot.events)
        self._header.update_header(snapshot.header)
        self._kpi.update_kpis(snapshot.kpis)
        self._conn.update_connections(snapshot.connections)
        self._orders.update_orders(snapshot.orders)
        self._events.set_events(self._events_buffer)

    def _append_events(self, events: Sequence[EventRow]) -> None:
        if not events:
            return
        self._events_buffer.extend(events)
        if len(self._events_buffer) > MAX_EVENT_BUFFER:
            self._events_buffer = self._events_buffer[-MAX_EVENT_BUFFER:]
        self._events.append_events(events)

    def _show_waiting(self, message: str) -> None:
        self._last_event_id = 0
        self._events_buffer.clear()
        self._header.show_message(message)
        self._kpi.show_message(message)
        self._conn.show_message(message)
        self._orders.show_message(message)
        self._events.show_message(message)

    def _show_error(self, message: str) -> None:
        self._header.show_message(message, style="red")
        self._kpi.show_message(message, style="red")
        self._conn.show_message(message, style="red")
        self._orders.show_message(message, style="red")
        self._events.show_message(message, style="red")

    async def action_quit(self) -> None:
        await self.shutdown()

    async def action_refresh(self) -> None:
        self._needs_snapshot = True
        await self._refresh_snapshot()

    async def on_key(self, event: events.Key) -> None:  # pragma: no cover - interactive
        if event.key.lower() == "q":
            await self.action_quit()
        elif event.key.lower() == "r":
            await self.action_refresh()


def main() -> None:
    app = DashboardApp()
    app.run()


if __name__ == "__main__":
    main()
