# bootstrap-marketlab.ps1
$ErrorActionPreference = "Stop"

# 1) Ordnerstruktur
$dirs = @(
  "src/marketlab",
  "src/marketlab/utils",
  "src/marketlab/data",
  "src/marketlab/modes"
)
$dirs | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }

# 2) pyproject.toml
@'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "marketlab"
version = "0.1.0"
description = "MarketLab – modular trading research sandbox (CLI, modes, adapters)"
authors = [{ name = "blanqspace" }]
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "pydantic>=2.7",
  "ib-insync>=0.9",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "mypy>=1.10",
  "ruff>=0.6",
  "black>=24.8",
]

[tool.ruff]
line-length = 100
select = ["E","F","I","UP","B"]

[tool.black]
line-length = 100

[tool.mypy]
python_version = "3.11"
warn_unused_ignores = true
strict = true
'@ | Set-Content -Encoding UTF8 -NoNewline pyproject.toml

# 3) README.md
@'
# MarketLab

Kurzüberblick
- Zweck: modulare Umgebung zum Analysieren, Testen und Simulieren von Marktdaten.
- Kernideen: klare Modi, einheitliche CLI, zentrale Settings, austauschbare Datenadapter.

## Quickstart
```bash
pip install -e .[dev]
marketlab --help
marketlab backtest --profile default --symbols AAPL,MSFT --timeframe 15m
