# tools/ibkr_status_interactive.py
import time
from ib_insync import IB, Stock, Forex

# Reihenfolge: Gateway Paper, Gateway Live, TWS Paper, TWS Live
CANDIDATE_PORTS = [4002, 4001, 7497, 7496]


def _auto_connect():
    ib = IB()
    for p in CANDIDATE_PORTS:
        try:
            ib.connect('127.0.0.1', p, clientId=700, timeout=5)
            if ib.isConnected():
                return ib, p
        except Exception:
            pass
    return None, None


def _header(ib: IB, port: int):
    t0 = time.time()
    srv = ib.reqCurrentTime()
    rtt = int((time.time() - t0) * 1000)

    client = getattr(ib, "client", None)
    sv = getattr(client, "serverVersion", None)
    tws = getattr(client, "twsConnectionTime", None)
    if callable(sv):
        try:
            sv = sv()
        except Exception:
            pass

    print("\n" + "═" * 72)
    print(f"✅ Connected: {ib.isConnected()} | ClientID: {ib.client.clientId} | Port: {port}")
    print(f"🕒 Serverzeit: {srv} | RTT: ~{rtt} ms")

    extras = []
    if sv is not None:
        extras.append(f"ServerVersion: {sv}")
    if tws:
        extras.append(f"TWS: {tws}")
    if extras:
        print("🧩 " + " | ".join(extras))
    print("─" * 72)


def _print_positions(ib: IB, limit: int = 10):
    pos = ib.positions()
    print(f"📊 Positionen: {len(pos)}")
    for p in pos[:limit]:
        c = p.contract
        sym = getattr(c, "symbol", str(c))
        cur = getattr(c, "currency", "")
        print(f"  • {sym} {p.position} @ {p.avgCost} {cur}")


def _hist_prompt(default_symbol="AAPL", default_duration="1 D", default_barsize="5 mins", default_type="stock"):
    sym = input(f"Symbol [{default_symbol}]: ").strip().upper() or default_symbol
    dur = input(f"Dauer (z.B. 1 D / 2 W / 6 M / 1 Y) [{default_duration}]: ").strip() or default_duration
    bs = input(f"Bar-Größe (z.B. 1 min / 5 mins / 15 mins / 1 hour / 1 day) [{default_barsize}]: ").strip() or default_barsize
    typ_in = input(f"Typ (stock/forex) [{default_type}]: ").strip().lower() or default_type
    typ = "forex" if typ_in.startswith("f") else "stock"
    return sym, dur, bs, typ


def _hist_fetch(ib: IB, symbol: str, duration: str, barsize: str, typ: str):
    if typ == "forex":
        contract = Forex(symbol)
    else:
        contract = Stock(symbol, "SMART", "USD")

    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=barsize,
            whatToShow="TRADES",
            useRTH=True
        )
    except Exception as e:
        print(f"❌ Fehler beim Laden der Historie für {symbol}: {e}")
        return

    n = len(bars)
    print(f"\n📈 Historie {symbol}  ·  {n} Bars  ·  Dauer={duration}  ·  Bar={barsize}")
    if n:
        print(f"   Zeitraum: {bars[0].date}  →  {bars[-1].date}")
        print("   Erste 3:")
        for b in bars[:3]:
            print(f"     {b.date}  O:{b.open} H:{b.high} L:{b.low} C:{b.close} V:{b.volume}")
        if n > 3:
            print("   Letzte 3:")
            for b in bars[-3:]:
                print(f"     {b.date}  O:{b.open} H:{b.high} L:{b.low} C:{b.close} V:{b.volume}")
    else:
        print("   Keine Daten (prüfe Symbol/Marktzugriff/Zeitraum).")


def main():
    ib, port = _auto_connect()
    if not ib:
        print("❌ Keine Verbindung auf 4002/4001/7497/7496.")
        print("• Starte IB Gateway (Paper) oder TWS")
        print("• API aktivieren: Enable ActiveX and Socket Clients")
        print("• Port prüfen (Gateway Paper=4002, TWS Paper=7497)")
        return

    try:
        _header(ib, port)

        accts = ib.managedAccounts()
        acct = accts[0] if accts else None
        print("👤 Accounts:", accts or "(keine)")

        if acct:
            tags = [
                "NetLiquidation", "AvailableFunds", "BuyingPower", "ExcessLiquidity",
                "MaintMarginReq", "GrossPositionValue", "CashBalance"
            ]
            summary = {e.tag: e.value for e in ib.accountSummary(acct) if e.tag in tags}
            print(f"💼 Account Summary ({acct}):", summary)

        print("─" * 72)
        opens = ib.openOrders()
        print(f"📋 Offene Orders: {len(opens)}")
        fills = ib.reqExecutions()
        print(f"✅ Ausführungen (heute): {len(fills)}")

        print("─" * 72)
        _print_positions(ib)
        print("─" * 72)
        ticks = ib.tickers()
        print(f"📡 Marktdaten-Subscriptions: {len(ticks)}")

        while True:
            s = input("\n[E]rneuern, [H]istorie, [Q]uit: ").strip().lower()
            if s in ("q", "quit"):
                break
            if s in ("h",):
                sym, dur, bs, typ = _hist_prompt()
                _hist_fetch(ib, sym, dur, bs, typ)
                continue
            if s in ("", "e", "r", "refresh"):
                _header(ib, port)
                if acct:
                    tags = [
                        "NetLiquidation", "AvailableFunds", "BuyingPower", "ExcessLiquidity",
                        "MaintMarginReq", "GrossPositionValue", "CashBalance"
                    ]
                    summary = {e.tag: e.value for e in ib.accountSummary(acct) if e.tag in tags}
                    print(f"💼 Account Summary ({acct}):", summary)
                print("─" * 72)
                opens = ib.openOrders()
                print(f"📋 Offene Orders: {len(opens)}")
                fills = ib.reqExecutions()
                print(f"✅ Ausführungen (heute): {len(fills)}")
                print("─" * 72)
                _print_positions(ib)
                print("─" * 72)
                ticks = ib.tickers()
                print(f"📡 Marktdaten-Subscriptions: {len(ticks)}")
            else:
                print("Bitte E, H oder Q.")
    finally:
        ib.disconnect()

# --- Symbol-Scan (Paper-Berechtigungen) -------------------------------------
def symbol_scan_cli():
    from shared.symbols.availability import discover, list_by
    print("Starte Symbol-Scan…")
    discover()  # scan + cache write
    print(f"Live:       {len(list_by('live'))}")
    print(f"Delayed:    {len(list_by('delayed'))}")
    print(f"Historical: {len(list_by('historical'))}")
    print(f"None:       {len(list_by('none'))}")



if __name__ == "__main__":
    main()
