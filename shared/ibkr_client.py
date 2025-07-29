import os
import asyncio
from ib_insync import IB
from shared.logger import get_logger
from shared.config_loader import get_env_var

logger = get_logger("ibkr_client")

class IBKRClient:
    def __init__(self, client_id: int = None, module: str = None):
        self.client_id = client_id or self._get_client_id_from_env(module)
        self.host = get_env_var("TWS_HOST", required=False) or "127.0.0.1"
        self.port = int(get_env_var("TWS_PORT", required=False) or 4002)
        self.ib = IB()

    def _get_client_id_from_env(self, module: str = None) -> int:
        if module:
            env_var = f"CLIENT_ID_{module.upper()}"
            return int(os.getenv(env_var, os.getenv("CLIENT_ID_DEFAULT", 127)))
        return int(os.getenv("CLIENT_ID_DEFAULT", 127))

    def connect(self) -> IB:
        try:
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"✅ Verbunden mit IBKR @ {self.host}:{self.port} (Client ID: {self.client_id})")
            return self.ib
        except Exception as e:
            logger.error(f"❌ Verbindung zu IBKR fehlgeschlagen: {e}")
            raise ConnectionError(f"IBKR-Verbindung fehlgeschlagen: {e}")

    def disconnect(self):
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info(f"✅ Verbindung zu IBKR getrennt (Client ID: {self.client_id})")
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Trennen von IBKR: {e}")
        finally:
            self.ib = None

    def is_connected(self) -> bool:
        return self.ib.isConnected()
