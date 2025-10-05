# shared/core/config_loader.py
from __future__ import annotations
import os
from dotenv import load_dotenv, find_dotenv

_loaded = False

def load_env() -> None:
    global _loaded
    if _loaded:
        return
    # 1) Basis .env laden, falls vorhanden
    base = find_dotenv(filename=".env", usecwd=True)
    if base:
        load_dotenv(base, override=False)
    # 2) Mode-spezifisch überschreiben
    mode = os.environ.get("ENV_MODE", "").strip()
    if mode:
        mode_file = find_dotenv(filename=f".env.{mode}", usecwd=True)
        if mode_file:
            load_dotenv(mode_file, override=True)
    _loaded = True

def get_env_var(key: str, *, required: bool = True, default: str | None = None) -> str | None:
    val = os.environ.get(key, default)
    if required and (val is None or val == ""):
        raise KeyError(f"Missing env var: {key}")
    return val
