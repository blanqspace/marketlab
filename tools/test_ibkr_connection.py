"""
Testskript: Verbindung & Datenabruf mit IBKR prüfen.
----------------------------------------------------
1. Verbindet sich mit IB Gateway oder TWS (Paper oder Live)
2. Prüft API-Zugang und Account-Infos
3. Ruft aktuelle Quotes ab
4. Ruft historische Kursdaten ab
5. Prüft, ob lokale CSV-/Parquet-Dateien importiert werden können
"""

from ib_insync import IB, Stock, util
import pandas as pd
from pathlib import Path
import os
import sys

# === Konfiguration ===
HOST = os.getenv("TWS_HOST", "127.0.0.1")
PORT = int(os.getenv("TWS_PORT", "4002"))
CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "7"))
SYMBOL = os.getenv("TEST_SYMBOL", "AAPL")
DATA_DIR = Path("data")

print("=" * 80)
print(f"📡 IBKR-Verbindungstest – Host={HOST} Port={PORT} ClientID={CLIENT_ID}")
print("=" * 80)

ib = IB()

try:
    ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=10)
    print("✅ Verbindung hergestellt!")
except Exception as e:
    print(f"❌ Verbindung fehlgeschlagen: {e}")
    sys.exit(1)

# === 1. Account prüfen ===
try:
    accs = ib.managedAccounts()
    print(f"📂 Accounts gefunden: {accs or 'Keine Accounts sichtbar'}")
except Exception as e:
    print(f"⚠️ Account-Check fehlgeschlagen: {e}")

# === 2. Echtzeitdaten (Quote) ===
try:
    contract = Stock(SYMBOL, 'SMART', 'USD')
    ticker = ib.reqMktData(contract)
    ib.sleep(3)
    print(f"💹 {SYMBOL}: bid={ticker.bid}, ask={ticker.ask}, last={ticker.last}")
    ib.cancelMktData(contract)
except Exception as e:
    print(f"⚠️ Echtzeitdaten fehlgeschlagen: {e}")

# === 3. Historische Daten ===
try:
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='1 D',
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    if bars:
        df = util.df(bars)
        print(f"📊 Historische Daten: {len(df)} Zeilen")
        print(df.head(3))
    else:
        print("⚠️ Keine historischen Daten empfangen.")
except Exception as e:
    print(f"⚠️ Historische Daten fehlgeschlagen: {e}")

# === 4. Lokale CSV-/Parquet-Imports prüfen ===
try:
    found = list(DATA_DIR.glob("*.csv")) + list(DATA_DIR.glob("*.parquet"))
    if not found:
        print("ℹ️ Keine lokalen Dateien gefunden unter /data.")
    else:
        for fp in found[:3]:
            if fp.suffix == ".csv":
                df = pd.read_csv(fp)
            else:
                df = pd.read_parquet(fp)
            print(f"📁 Datei geladen: {fp.name} – {len(df)} Zeilen, Spalten: {list(df.columns)[:6]}")
except Exception as e:
    print(f"⚠️ Import-Test fehlgeschlagen: {e}")

# === 5. Sauber beenden ===
ib.disconnect()
print("✅ Test abgeschlossen – Verbindung getrennt.")
print("=" * 80)