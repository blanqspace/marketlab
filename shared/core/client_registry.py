import os
import json
from pathlib import Path
from typing import Union, List, Optional, Dict

from shared.utils.logger import get_logger
from shared.utils.file_utils import load_json_file

logger = get_logger("client_registry")

DEFAULT_ID_MAP = {
    "data_manager": 101,
    "order_executor": 102,
    "realtime": 103,
    "account": 104,
    "symbol_fetcher_pool": list(range(105, 120)),
    "strategy_lab": 121
}

CONFIG_PATH = Path("config/client_ids.json")


class ClientRegistry:
    def __init__(self):
        self.id_map = self._load_ids()
        self.status_map: Dict[int, Dict[str, Union[str, bool]]] = {}

    def _load_ids(self) -> Dict[str, Union[int, List[int]]]:
        if CONFIG_PATH.exists():
            data = load_json_file(CONFIG_PATH, fallback=DEFAULT_ID_MAP, expected_type=dict)
            logger.info("✅ client_ids.json geladen")
            return data
        else:
            logger.warning("⚠️ client_ids.json nicht gefunden – verwende Default-Zuordnung")
            return DEFAULT_ID_MAP.copy()

    def get_client_id(self, module: str) -> Optional[int]:
        entry = self.id_map.get(module)
        if isinstance(entry, int):
            return entry
        elif isinstance(entry, list) and entry:
            return entry[0]
        logger.error(f"❌ Keine Client-ID für Modul '{module}' gefunden")
        return None

    def get_pool(self, key: str) -> List[int]:
        pool = self.id_map.get(key, [])
        if isinstance(pool, list):
            return pool
        return []

    def get_all_ids(self) -> List[int]:
        ids = []
        for val in self.id_map.values():
            if isinstance(val, int):
                ids.append(val)
            elif isinstance(val, list):
                ids.extend(val)
        return sorted(set(ids))

    def get_free_id_from_pool(self, pool_name: str) -> Optional[int]:
        pool = self.get_pool(pool_name)
        active_ids = set(self.status_map.keys())
        for cid in pool:
            if cid not in active_ids:
                logger.info(f"🟢 Freie Client-ID gefunden: {cid} aus Pool '{pool_name}'")
                return cid
        logger.warning(f"⚠️ Keine freie ID mehr im Pool '{pool_name}'")
        return None

    def assign_next_free_id(self, task_name: str, pool_name: str = "symbol_fetcher_pool") -> Optional[int]:
        cid = self.get_free_id_from_pool(pool_name)
        if cid is not None:
            self.set_status(cid, task_name, connected=False)
        return cid

    def set_status(self, client_id: int, task: str, connected: bool) -> None:
        self.status_map[client_id] = {
            "task": task,
            "connected": connected
        }

    def update_connected(self, client_id: int, connected: bool = True):
        if client_id in self.status_map:
            self.status_map[client_id]["connected"] = connected

    def get_status_report(self) -> str:
        lines = ["🧩 Client-ID-Status:"]
        for cid, info in sorted(self.status_map.items()):
            lines.append(f"  {cid}: {info.get('task')} – {'✅ verbunden' if info.get('connected') else '⛔️ getrennt'}")
        return "\n".join(lines)


registry = ClientRegistry()
registry.set_status(199, task="symbol_probe", connected=False)
