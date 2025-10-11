param()
$ErrorActionPreference = 'Stop'
Write-Host "Starting Worker Daemon"
python -c "from src.marketlab.daemon.worker import run_forever; run_forever()"

