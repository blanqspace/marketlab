# shared/ibkr/ibkr_client.py
from __future__ import annotations
import os
import asyncio
from ib_insync import IB, Contract
from shared.utils.logger import get_logger
from shared.core.client_registry import registry  # globales Singleton

logger = get_logger("ibkr_client")


class IBKRClient:
    """
    Dünner Wrapper um ib_insync.IB mit Registry-Status.
    - Vergibt Client-ID anhand Registry (wenn module angegeben)
    - Meldet Verbindungsstatus in der Registry
    - Context-Manager: with IBKRClient(...) as ib:
    """

    def __init__(self, client_id: int | None = None, module: str | None = None, task: str | None = None):
        """
        Args:
            client_id: explizite IBKR-Client-ID (optional)
            module: z. B. "data_manager", "symbol_fetcher_pool", "realtime"
            task: freier Task-Name für Status/Monitoring (z. B. "fetch_AAPL")
        """
        self.module = module
        self.task = task or module or "unbenannt"
        self.client_id = client_id or self._resolve_client_id()
        self.host = os.getenv("TWS_HOST", "127.0.0.1")
        self.port = int(os.getenv("TWS_PORT", 4002))
        self.ib = IB()

        # initialer Status (noch nicht verbunden)
        registry.set_status(self.client_id, self.task, connected=False, module=self.module)

    # ── Context-Manager ─────────────────────────────────────────────────────

    def __enter__(self) -> IB:
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.disconnect()
        return False  # Exception nicht unterdrücken

    # ── Client-ID Auflösung ─────────────────────────────────────────────────

    def _resolve_client_id(self) -> int:
        if self.module:
            if self.module.endswith("_pool"):
                cid = registry.assign_next_free_id(task_name=self.task, pool_name=self.module)
                if cid is not None:
                    return cid
            else:
                cid = registry.get_client_id(self.module)
                if cid is not None:
                    return cid
        logger.warning("⚠️ Keine gültige client_id gefunden – Fallback 127")
        return 127

    # ── Verbindungssteuerung ────────────────────────────────────────────────

    def connect(self, auto_reconnect: bool = False) -> IB:
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"✅ Verbunden @ {self.host}:{self.port} (Client ID: {self.client_id})")
            registry.update_connected(self.client_id, connected=True)

            if auto_reconnect:
                self.ib.setCallback('disconnected', self._on_disconnect)

            return self.ib
        except Exception as e:
            logger.error(f"❌ Verbindung zu IBKR fehlgeschlagen: {e}")
            registry.update_connected(self.client_id, connected=False)
            raise ConnectionError(f"IBKR-Verbindung fehlgeschlagen: {e}") from e

    def _on_disconnect(self):
        logger.warning("⚠️ IBKR-Verbindung verloren – Status aktualisiert")
        registry.update_connected(self.client_id, connected=False)

    def disconnect(self):
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info(f"✅ Verbindung getrennt (Client ID: {self.client_id})")
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Trennen: {e}")
        finally:
            registry.update_connected(self.client_id, connected=False)
            self.ib = IB()  # frische Instanz

    # ── Status ──────────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self.ib.isConnected()

    def status(self) -> dict:
        if not self.is_connected():
            return {
                "connected": False,
                "client_id": self.client_id,
                "task": self.task,
                "host": self.host,
                "port": self.port,
            }
        try:
            return {
                "connected": True,
                "client_id": self.client_id,
                "task": self.task,
                "host": self.host,
                "port": self.port,
                "server_time": str(self.ib.serverTime()),
                "tws_version": self.ib.twsConnectionTime(),
                "account_list": self.ib.managedAccounts(),
            }
        except Exception as e:
            return {"connected": True, "client_id": self.client_id, "task": self.task, "warning": str(e)}

    # ── Hilfen: Contracts & Preise ──────────────────────────────────────────

    def qualify_or_raise(self, c: Contract) -> Contract:
        """Qualifiziert Contract. Wirft klaren Fehler bei Unknown Contract."""
        qc = self.ib.qualifyContracts(c)
        if not qc or not getattr(qc[0], "conId", 0):
            sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
            raise ValueError(f"Unknown contract: {sym}")
        return qc[0]

    def mid_or_last(self, c: Contract, delay_ok: bool = True) -> float | None:
        """Mid, sonst last/close. None wenn nichts verfügbar."""
        try:
            self.ib.reqMarketDataType(3 if delay_ok else 1)
        except Exception:
            pass
        t = self.ib.reqMktData(c, "", False, False)
        self.ib.sleep(0.8)
        try:
            bid = getattr(t, "bid", None)
            ask = getattr(t, "ask", None)
            if bid and ask:
                return (bid + ask) / 2
            return getattr(t, "last", None) or getattr(t, "close", None)
        finally:
            try:
                self.ib.cancelMktData(t)
            except Exception:
                pass

    def fetch_hist(self, contract: Contract, *, duration: str, barsize: str,
                   what: str = "TRADES", rth: bool = True):
        """
        Wrapper um reqHistoricalData. Existiert hier, damit Menü/Module das konsistent nutzen.
        """
        c = self.qualify_or_raise(contract)
        return self.ib.reqHistoricalData(
            c,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=barsize,
            whatToShow=what,
            useRTH=rth,
        )

