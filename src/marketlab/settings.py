from enum import Enum
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class ClientRole(str, Enum):
    MAIN = "MAIN"
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    REPLAY = "REPLAY"

class IBKRSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
    host: str = Field("127.0.0.1", alias="TWS_HOST")
    port: int = Field(7497, alias="TWS_PORT")

class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
    enabled: bool = Field(False, alias="TELEGRAM_ENABLED")
    bot_token: SecretStr | None = Field(None, alias="TELEGRAM_BOT_TOKEN")
    chat_control: str | None = Field(None, alias="TG_CHAT_CONTROL")

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    env_mode: str = Field("DEV", alias="ENV_MODE")
    ibkr: IBKRSettings = IBKRSettings()
    telegram: TelegramSettings = TelegramSettings()

class RuntimeConfig(BaseModel):
    profile: str
    symbols: list[str]
    timeframe: str

settings = AppSettings()
