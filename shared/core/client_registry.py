# shared/core/client_registry.py
import json
import threading
from pathlib import Path
from typing import Union, List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

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
STORE_DIR = Path("runtime/clients")
STORE_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = STORE_DIR / "status.json"

UTC = timezone.utc


class ClientRegistry:
    """
    Prozessübergreifende, persistente Registry:
    - IDs & Pools aus config/client_ids.json (oder Defaults)
    - Status/Tätigkeiten in runtime/clients/status.json
    - Heartbeat/letzte Aktivität
    """
    def __init__(self):
        self.id_map = self._load_ids()
        self.status_map: Dict[int, Dict[str, Union[str, bool, int, float]]] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    # ── Konfiguration ────────────────────────────────────────────────────────
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
            self.set_status(cid, task_name, connected=False, module=pool_name)
        return cid

    # ── Persistenz ──────────────────────────────────────────────────────────
    def _load_persisted(self) -> None:
        try:
            if STORE_PATH.exists():
                data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    with self._lock:
                        self.status_map.update({int(k): v for k, v in data.items()})
                logger.info(f"💾 Registry-Status geladen ({STORE_PATH})")
        except Exception as e:
            logger.warning(f"⚠️ Registry-Status konnte nicht geladen werden: {e}")

    def _persist(self) -> None:
        try:
            with self._lock:
                STORE_PATH.write_text(json.dumps(self.status_map, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Registry-Status konnte nicht gespeichert werden: {e}")

    # ── Status/Heartbeat ────────────────────────────────────────────────────
    def set_status(self, client_id: int, task: str, connected: bool, module: Optional[str] = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            entry = self.status_map.get(client_id, {})
            entry.update({
                "task": task,
                "module": module or entry.get("module", ""),
                "connected": connected,
                "first_seen": entry.get("first_seen", now),
                "last_update": now,
                "last_heartbeat": entry.get("last_heartbeat", now) if connected else entry.get("last_heartbeat", None),
            })
            self.status_map[client_id] = entry
        self._persist()

    def update_connected(self, client_id: int, connected: bool = True):
        with self._lock:
            entry = self.status_map.get(client_id, {})  # falls noch nicht gesetzt
            entry.setdefault("task", "")
            entry.setdefault("module", "")
            entry["connected"] = connected
            entry["last_update"] = datetime.now(UTC).isoformat()
            if connected:
                entry["last_heartbeat"] = datetime.now(UTC).isoformat()
            self.status_map[client_id] = entry
        self._persist()

    def register_heartbeat(self, client_id: int) -> None:
        with self._lock:
            if client_id not in self.status_map:
                self.status_map[client_id] = {"task": "", "module": "", "connected": True, "first_seen": datetime.now(UTC).isoformat()}
            self.status_map[client_id]["last_heartbeat"] = datetime.now(UTC).isoformat()
            self.status_map[client_id]["last_update"] = datetime.now(UTC).isoformat()
        self._persist()

    # ── Abfragen/Reports ────────────────────────────────────────────────────
    def get_active_ids(self, heartbeat_timeout_sec: int = 60) -> List[int]:
        """
        IDs, die entweder verbunden sind oder in den letzten 'heartbeat_timeout_sec' ein Lebenszeichen hatten.
        """
        active: List[int] = []
        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_timeout_sec)
        with self._lock:
            for cid, info in self.status_map.items():
                if info.get("connected"):
                    active.append(cid)
                    continue
                hb = info.get("last_heartbeat")
                if hb:
                    try:
                        ts = datetime.fromisoformat(hb)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=UTC)
                        if ts >= cutoff:
                            active.append(cid)
                    except Exception:
                        pass
        return sorted(set(active))

    def get_status_report(self) -> str:
        lines = ["🧩 Client-ID-Status:"]
        with self._lock:
            for cid in sorted(self.status_map.keys()):
                info = self.status_map[cid]
                state = "✅ verbunden" if info.get("connected") else "⛔️ getrennt"
                task = info.get("task", "")
                module = info.get("module", "")
                hb = info.get("last_heartbeat", "-")
                upd = info.get("last_update", "-")
                lines.append(f"  {cid}: {task} [{module}] – {state} – last_hb: {hb} – upd: {upd}")
        return "\n".join(lines)


# Singleton-Instanz (projektweit verwenden)
registry = ClientRegistry()

# (Optional) vordefinierte, „reservierte“ ID sichtbar machen
registry.set_status(199, task="symbol_probe", connected=False, module="internal")
