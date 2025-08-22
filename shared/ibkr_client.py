#shared\ibkr_client.py
import os
import asyncio
from ib_insync import IB
from shared.logger import get_logger
from shared.client_registry import ClientRegistry

logger = get_logger("ibkr_client")

registry = ClientRegistry()


class IBKRClient:
    def __init__(self, client_id: int = None, module: str = None, task: str = None):
        """
        client_id = explizit angeben (optional)
        module = z. B. "data_manager", "symbol_fetcher_pool"
        task = optional: wird für Statusübersicht verwendet (z. B. "fetch_AAPL")
        """
        self.module = module
        self.task = task or module or "unbenannt"
        self.client_id = client_id or self._resolve_client_id()
        self.host = os.getenv("TWS_HOST", "127.0.0.1")
        self.port = int(os.getenv("TWS_PORT", 4002))
        self.ib = IB()

        registry.set_status(self.client_id, self.task, connected=False)

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
        logger.warning("⚠️ Keine gültige client_id gefunden – verwende Fallback-ID 127")
        return 127

    def connect(self, auto_reconnect: bool = False) -> IB:
        """
        Stellt Verbindung her, meldet Status an Registry
        """
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"✅ Verbunden mit IBKR @ {self.host}:{self.port} (Client ID: {self.client_id})")
            registry.update_connected(self.client_id, connected=True)

            if auto_reconnect:
                self.ib.setCallback('disconnected', self._on_disconnect)

            return self.ib
        except Exception as e:
            logger.error(f"❌ Verbindung zu IBKR fehlgeschlagen: {e}")
            registry.update_connected(self.client_id, connected=False)
            raise ConnectionError(f"IBKR-Verbindung fehlgeschlagen: {e}")

    def _on_disconnect(self):
        logger.warning("⚠️ IBKR-Verbindung verloren – Status aktualisiert")
        registry.update_connected(self.client_id, connected=False)

    def disconnect(self):
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info(f"✅ Verbindung zu IBKR getrennt (Client ID: {self.client_id})")
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Trennen von IBKR: {e}")
        finally:
            registry.update_connected(self.client_id, connected=False)
            self.ib = IB()  # Reset

    def is_connected(self) -> bool:
        return self.ib.isConnected()

    def status(self) -> dict:
        if not self.is_connected():
            return {
                "connected": False,
                "client_id": self.client_id,
                "task": self.task,
                "host": self.host,
                "port": self.port
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
                "account_list": self.ib.managedAccounts()
            }
        except Exception as e:
            return {
                "connected": True,
                "client_id": self.client_id,
                "task": self.task,
                "warning": str(e)
            }
