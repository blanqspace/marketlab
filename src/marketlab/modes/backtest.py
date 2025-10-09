from ..data.adapters import CSVAdapter
from ..core.state_manager import STATE

def run(settings, profile: str="default", symbols: str="", timeframe: str="15m", start=None, end=None, work_units: int=0):
    STATE.set_mode("backtest")
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise ValueError("Keine Symbole angegeben. Beispiel: --symbols AAPL,MSFT")

    adapter = CSVAdapter(base_dir="data")
    total_loaded = 0
    for sym in sym_list:
        bars = adapter.load_bars(symbol=sym, timeframe=timeframe, start=start, end=end)
        if bars is None or len(bars) == 0:
            # nur Warnung; wir fahren fort, um mehrere Symbole zu erlauben
            STATE.post({"level": "warning", "msg": f"{sym}/{timeframe}: keine Daten gefunden"})
            continue
        total_loaded += len(bars)
        STATE.post({"symbol": sym, "processed": len(bars)})

    if total_loaded == 0:
        raise FileNotFoundError("Backtest: Keine Daten gefunden. Erwartet: data/SYMBOL_TIMEFRAME.csv|parquet mit Spalten time,open,high,low,close,volume")

    return {"symbols": sym_list, "total": total_loaded}

