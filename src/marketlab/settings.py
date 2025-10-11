from enum import Enum
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pydantic import field_validator

class ClientRole(str, Enum):
    MAIN = "MAIN"
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    REPLAY = "REPLAY"

class IBKRSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    enabled: bool = Field(False, alias="IBKR_ENABLED")
    # Provide sensible defaults so non-IBKR commands still work without env
    host: str = Field("127.0.0.1", alias="TWS_HOST")
    port: int = Field(4002, alias="TWS_PORT")
    client_id: int = Field(7, alias="IBKR_CLIENT_ID")

class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    enabled: bool = Field(False, alias="TELEGRAM_ENABLED")
    bot_token: Optional[SecretStr] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    chat_control: Optional[int] = Field(None, alias="TG_CHAT_CONTROL")
    mock: bool = Field(False, alias="TELEGRAM_MOCK")
    timeout_sec: int = Field(25, alias="TELEGRAM_TIMEOUT_SEC")
    debug: bool = Field(False, alias="TELEGRAM_DEBUG")
    allowlist: List[int] = Field(default_factory=list, alias="TG_ALLOWLIST")

    @field_validator("allowlist", mode="before")
    @classmethod
    def _coerce_allowlist(cls, v):
        if v is None:
            return []
        # Already a list
        if isinstance(v, list):
            return [int(x) for x in v if str(x).strip()]
        # Single int
        if isinstance(v, int):
            return [v]
        # Comma-separated string
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            out: List[int] = []
            for p in parts:
                try:
                    out.append(int(p))
                except Exception:
                    continue
            return out
        try:
            return list(v)
        except Exception:
            return []

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    env_mode: str = Field("DEV", alias="ENV_MODE")
    app_brand: str = Field("MarketLab", alias="APP_BRAND")
    # IPC / worker related
    ipc_db: str = Field("runtime/ctl.db", alias="IPC_DB")
    orders_two_man_rule: bool = Field(True, alias="ORDERS_TWO_MAN_RULE")
    confirm_strict: bool = Field(True, alias="CONFIRM_STRICT")
    # Orders UX
    orders_token_len: int = Field(6, alias="ORDERS_TOKEN_LEN")
    orders_show_recent: int = Field(6, alias="ORDERS_SHOW_RECENT")
    # Dashboard refresh cadence (seconds)
    events_refresh_sec: int = Field(2, alias="EVENTS_REFRESH_SEC")
    kpis_refresh_sec: int = Field(15, alias="KPIS_REFRESH_SEC")
    # Dashboard event filter toggle
    dashboard_warn_only: int = Field(0, alias="DASHBOARD_WARN_ONLY")
    ibkr: IBKRSettings = IBKRSettings()
    telegram: TelegramSettings = TelegramSettings()

class RuntimeConfig(BaseModel):
    profile: str
    symbols: list[str]
    timeframe: str

settings = AppSettings()

def get_settings() -> AppSettings:
    return settings
