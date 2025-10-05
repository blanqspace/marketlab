# tools/start_marketlab.ps1
$env:ENV_MODE="PROD"
$env:TWS_HOST="127.0.0.1"
$env:TWS_PORT="7497"
$env:TELEGRAM_ENABLED="false"

# Arbeitsverzeichnis auf Repo-Root setzen
Set-Location -Path "C:\Users\shaba\OneDrive\Anlagen\marketlab"

# Start: Beispiel Backtest
python -m marketlab backtest --profile default --symbols AAPL,MSFT --timeframe 15m `
  *> "logs\auto_start_$(Get-Date -f yyyyMMdd_HHmmss).log"
