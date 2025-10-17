import os, json
print({
    "mock": os.getenv("TELEGRAM_MOCK"),
    "enabled": os.getenv("TELEGRAM_ENABLED"),
    "brand": os.getenv("APP_BRAND"),
})

