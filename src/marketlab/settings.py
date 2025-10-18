from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    bot_token: SecretStr | None = Field(None, alias="TELEGRAM_BOT_TOKEN")
    chat_control: int | None = Field(None, alias="TG_CHAT_CONTROL")
    mock: bool = Field(False, alias="TELEGRAM_MOCK")
    timeout_sec: int = Field(20, alias="TELEGRAM_TIMEOUT_SEC")
    long_poll_sec: int = Field(20, alias="TELEGRAM_LONG_POLL_SEC")
    debug: bool = Field(True, alias="TELEGRAM_DEBUG")
    allowlist: list[int] | str = Field(default_factory=list, alias="TG_ALLOWLIST")
    command_pin: str | None = Field(None, alias="TG_CMD_PIN")
    rate_limit_per_min: int = Field(10, alias="TG_RATE_LIMIT_PER_MIN")

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
            out: list[int] = []
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
    orders_ttl_seconds: int = Field(300, alias="ORDERS_TTL_SECONDS")
    # Orders UX
    orders_token_len: int = Field(6, alias="ORDERS_TOKEN_LEN")
    orders_show_recent: int = Field(6, alias="ORDERS_SHOW_RECENT")
    # Dashboard refresh cadence (seconds)
    events_refresh_sec: int = Field(5, alias="EVENTS_REFRESH_SEC")
    kpis_refresh_sec: int = Field(15, alias="KPIS_REFRESH_SEC")
    # Dashboard event filter toggle
    dashboard_warn_only: int = Field(0, alias="DASHBOARD_WARN_ONLY")
    ibkr: IBKRSettings = IBKRSettings()
    telegram: TelegramSettings = TelegramSettings()

    # --- Compatibility accessors (flat-style) ---
    @property
    def TELEGRAM_ENABLED(self) -> bool:  # pragma: no cover
        return bool(self.telegram.enabled)

    @property
    def TELEGRAM_MOCK(self) -> bool:  # pragma: no cover
        return bool(self.telegram.mock)

    @property
    def TELEGRAM_BOT_TOKEN(self) -> str:  # pragma: no cover
        try:
            return self.telegram.bot_token.get_secret_value() if self.telegram.bot_token else ""
        except Exception:
            return str(self.telegram.bot_token) if self.telegram.bot_token else ""

    @property
    def TG_CHAT_CONTROL(self) -> int | None:  # pragma: no cover
        return self.telegram.chat_control

    @property
    def TG_ALLOWLIST(self) -> list[int]:  # pragma: no cover
        return list(self.telegram.allowlist or [])

    @property
    def TELEGRAM_TIMEOUT_SEC(self) -> int:  # pragma: no cover
        return int(self.telegram.timeout_sec)

    @property
    def TELEGRAM_LONG_POLL_SEC(self) -> int:  # pragma: no cover
        return int(self.telegram.long_poll_sec)

    @property
    def TELEGRAM_DEBUG(self) -> bool:  # pragma: no cover
        return bool(self.telegram.debug)

class RuntimeConfig(BaseModel):
    profile: str
    symbols: list[str]
    timeframe: str

@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Lädt .env + OS-ENV einmalig und cached die App-Settings."""
    return AppSettings()

# Keep a module-level reference for legacy code/tests
settings = get_settings()

# --- Backward compatibility ---
# Some code may still import `Settings` from this module.
# Provide an alias to the new `AppSettings` to avoid ImportError.
Settings = AppSettings  # pragma: no cover
