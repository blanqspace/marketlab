# 🗂️ Projektdateien (gezielte Übersicht)


## `..\config\active_symbols.json`
- 📄 Zeilen: 7, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
{
  "symbols": [
    "AAPL",
    "MSFT",
    "SPY"
  ]
}
```

## `..\config\cached_symbols.json`
- 📄 Zeilen: 8, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
{
  "symbols": [
    "AAPL",
    "SPY",
    "TSLA"
  ],
  "fetched_at": "2025-07-30T02:34:56"
}
```

## `..\config\client_ids.json`
- 📄 Zeilen: 15, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
{
  "data_manager": 101,
  "order_executor": 102,
  "realtime": 103,
  "symbol_fetcher_pool": [
    105,
    106,
    107,
    108,
    109,
    110
  ],
  "strategy_lab": 110,
  "symbol_probe": 199
}
```

## `..\config\healthcheck_config.json`
- 📄 Zeilen: 13, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
[
  {
    "name": "IBKR Gateway",
    "type": "tcp",
    "host": "127.0.0.1",
    "port": 4002
  },
  {
    "name": "Price API",
    "type": "http",
    "url": "https://httpbin.org/status/200"
  }
]
```

## `..\config\startup.json`
- 📄 Zeilen: 9, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
{
  "modules": {
    "health": false,
    "data_fetcher": false,
    "symbol_fetcher": true,
    "order_manager": false,
    "dispatcher": false
  }
}
```

## `..\config\symbol_availability.json`
- 📄 Zeilen: 22, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
{
  "AAPL": {
    "live": false,
    "historical": true
  },
  "GOOG": {
    "live": false,
    "historical": true
  },
  "MSFT": {
    "live": false,
    "historical": true
  },
  "EURUSD": {
    "live": true,
    "historical": false
  },
  "ES": {
    "live": false,
    "historical": false
  }
}
```

## `..\config\symbol_tasks.json`
- 📄 Zeilen: 22, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
[
  {
    "symbol": "AAPL",
    "active": true
  },
  {
    "symbol": "MSFT",
    "active": true
  },
  {
    "symbol": "GOOG",
    "active": false
  },
  {
    "symbol": "SPY",
    "active": true
  },
  {
    "symbol": "TSLA",
    "active": true
  }
]
```

## `..\config\tasks.json`
- 📄 Zeilen: 23, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
[
  {
    "name": "import_AAPL_local",
    "symbol": "AAPL",
    "url": "file://data/AAPL.csv",
    "active": true,
    "save": false
  },
  {
    "name": "import_MSFT_http",
    "symbol": "MSFT",
    "url": "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv",
    "active": false,
    "save": true
  },
  {
    "name": "import_FAKE_404",
    "symbol": "FAKE",
    "url": "https://example.com/404-data.csv",
    "active": false,
    "save": false
  }
]
```

## `..\config\profiles\current.json`
- 📄 Zeilen: 0, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
```

## `..\config\profiles\default.json`
- 📄 Zeilen: 0, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```json
```