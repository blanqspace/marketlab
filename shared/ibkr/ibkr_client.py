# shared/ibkr/ibkr_client.py
from __future__ import annotations
import os
import asyncio
from ib_insync import IB, Contract
from shared.utils.logger import get_logger
from shared.core.client_registry import registry  # Singleton aus deinem Projekt

logger = get_logger("ibkr_client")


class IBKRClient:
    """
    Dünner Wrapper um ib_insync.IB mit Registry-Status.
    - Vergibt Client-ID aus registry (wenn module angegeben)
    - Meldet Verbindungsstatus in registry
    - Context-Manager: with IBKRClient(...) as ib:
    """

    def __init__(self, client_id: int | None = None, module: str | None = None, task: str | None = None):
        self.module = module
        self.task = task or module or "unbenannt"
        self.client_id = client_id or self._resolve_client_id()
        self.host = os.getenv("TWS_HOST", "127.0.0.1")
        self.port = int(os.getenv("TWS_PORT", 4002))
        self.ib = IB()
        self._auto_reconnect = False  # merkt, ob wir Event registriert haben

        registry.set_status(self.client_id, self.task, connected=False, module=self.module)

    # ── Context-Manager ─────────────────────────────────────────────
    def __enter__(self) -> IB:
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.disconnect()
        return False

    # ── Client-ID Auflösung ────────────────────────────────────────
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

    # ── Verbindungssteuerung ───────────────────────────────────────
    def connect(self, auto_reconnect: bool = False) -> IB:
        try:
            # eigenen asyncio-Loop sicherstellen (ib_insync nutzt asyncio)
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"✅ Verbunden @ {self.host}:{self.port} (Client ID: {self.client_id})")
            registry.update_connected(self.client_id, connected=True)

            self._auto_reconnect = bool(auto_reconnect)
            if self._auto_reconnect:
                # korrektes Event-Modell von ib_insync
                try:
                    self.ib.disconnectedEvent += self._on_disconnect  # type: ignore[attr-defined]
                except Exception:
                    pass

            return self.ib
        except Exception as e:
            logger.error(f"❌ Verbindung zu IBKR fehlgeschlagen: {e}")
            registry.update_connected(self.client_id, connected=False)
            raise ConnectionError(f"IBKR-Verbindung fehlgeschlagen: {e}") from e

    def _on_disconnect(self, *args, **kwargs):
        logger.warning("⚠️ IBKR-Verbindung verloren – Status aktualisiert")
        registry.update_connected(self.client_id, connected=False)

    def disconnect(self):
        try:
            # Event deregistrieren, falls wir es registriert hatten
            if self._auto_reconnect:
                try:
                    self.ib.disconnectedEvent -= self._on_disconnect  # type: ignore[attr-defined]
                except Exception:
                    pass

            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info(f"✅ Verbindung getrennt (Client ID: {self.client_id})")
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Trennen: {e}")
        finally:
            registry.update_connected(self.client_id, connected=False)
            self.ib = IB()  # frische Instanz

    # ── Status ─────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        return getattr(self.ib, "isConnected", lambda: False)()

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
            sv = None
            try:
                sv_attr = getattr(self.ib.client, "serverVersion", None)
                sv = sv_attr() if callable(sv_attr) else sv_attr
            except Exception:
                sv = None

            return {
                "connected": True,
                "client_id": self.client_id,
                "task": self.task,
                "host": self.host,
                "port": self.port,
                "server_time": str(self.ib.reqCurrentTime()),
                "tws_version": sv,
                "account_list": self.ib.managedAccounts(),
            }
        except Exception as e:
            return {"connected": True, "client_id": self.client_id, "task": self.task, "warning": str(e)}

    # ── Hilfen: Contracts & Preise ─────────────────────────────────
    def qualify_or_raise(self, c: Contract) -> Contract:
        qc = self.ib.qualifyContracts(c)
        if not qc or not getattr(qc[0], "conId", 0):
            sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
            raise ValueError(f"Unknown contract: {sym}")
        return qc[0]

    def mid_or_last(self, c: Contract, delay_ok: bool = True) -> float | None:
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
        c = self.qualify_or_raise(contract)
        return self.ib.reqHistoricalData(
            c,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=barsize,
            whatToShow=what,
            useRTH=rth,
        )
