from enum import Enum
from pydantic import BaseModel, BaseSettings, Field, SecretStr
from typing import Optional

class ClientRole(str, Enum):
    MAIN = "MAIN"
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    REPLAY = "REPLAY"

class IBKRSettings(BaseSettings):
    host: str = Field(..., alias="TWS_HOST")
    port: int = Field(..., alias="TWS_PORT")

class TelegramSettings(BaseSettings):
    enabled: bool = Field(False, alias="TELEGRAM_ENABLED")
    bot_token: Optional[SecretStr] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    chat_control: Optional[int] = Field(None, alias="TG_CHAT_CONTROL")
    allowlist_csv: Optional[str] = Field(None, alias="TG_ALLOWLIST")

class AppSettings(BaseSettings):
    env_mode: str = Field("DEV", alias="ENV_MODE")
    app_brand: str = Field("MarketLab", alias="APP_BRAND")
    ibkr: IBKRSettings = IBKRSettings()
    telegram: TelegramSettings = TelegramSettings()

class RuntimeConfig(BaseModel):
    profile: str
    symbols: list[str]
    timeframe: str

settings = AppSettings()
