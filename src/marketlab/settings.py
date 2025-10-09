from enum import Enum
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class ClientRole(str, Enum):
    MAIN = "MAIN"
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    REPLAY = "REPLAY"

class IBKRSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    host: str = Field(..., alias="TWS_HOST")
    port: int = Field(..., alias="TWS_PORT")

class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    enabled: bool = Field(False, alias="TELEGRAM_ENABLED")
    bot_token: Optional[SecretStr] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    chat_control: Optional[int] = Field(None, alias="TG_CHAT_CONTROL")
    allowlist_csv: Optional[str] = Field(None, alias="TG_ALLOWLIST")
    mock: bool = Field(False, alias="TELEGRAM_MOCK")  # NEW

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    env_mode: str = Field("DEV", alias="ENV_MODE")
    app_brand: str = Field("MarketLab", alias="APP_BRAND")
    ibkr: IBKRSettings = IBKRSettings()
    telegram: TelegramSettings = TelegramSettings()

class RuntimeConfig(BaseModel):
    profile: str
    symbols: list[str]
    timeframe: str

settings = AppSettings()

def get_settings() -> AppSettings:
    return settings
