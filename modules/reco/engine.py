# modules/reco/engine.py
from __future__ import annotations

import json, sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

# Project root on sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.data.ingest import ingest_one, read_csv_rows  # vorhandene Funktionen

# ---------- kleine Helfer ----------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _safe_bar(b: str) -> str:
    return (b or "").replace(" ", "")

def _print(s: str):
    # zentrale Stelle – falls du später in Logger umleiten willst
    print(s)

def _sma(series: List[float], window: int) -> List[Optional[float]]:
    out = [None] * len(series)
    s = 0.0
    for i, v in enumerate(series):
        s += v
        if i >= window:
            s -= series[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out

def _interpret(signal: str, conf: float, reason: str) -> str:
    band = "schwach"
    if conf >= 0.75: band = "stark"
    elif conf >= 0.6: band = "mittel"
    if signal in ("BUY", "SELL"):
        return f"{signal} ({band}, conf={conf:.2f}). Begründung: {reason}"
    if signal.startswith("HOLD_"):
        richt = "aufwärts" if signal.endswith("UP") else "abwärts"
        return f"Halten/Beobachten ({band}): Trend {richt}. Begründung: {reason}"
    return f"{signal}: {reason}"

# ---------- Daten laden / vorbereiten ----------
def _ensure_clean_csv(sym: str, preset: dict, trace: List[str]) -> Path:
    asset = preset["asset"]; barsize = preset["barsize"]; safe_bar = _safe_bar(barsize)
    clean_path = Path(f"data_clean/{asset}_{sym}_{safe_bar}.csv")
    if clean_path.exists():
        trace.append(f"✔ Cache: {clean_path} vorhanden")
        return clean_path

    # Kein Clean vorhanden → versuche Ingest
    trace.append(f"→ Ingest starte: {sym} | {asset} | {preset['duration']} | {barsize} | {preset['what']} | RTH={bool(preset.get('rth', True))}")
    try:
        manifest = ingest_one(
            symbol=sym,
            asset=asset,
            duration=preset["duration"],
            barsize=preset["barsize"],
            what=preset["what"],
            rth=bool(preset.get("rth", True)),
            overwrite=False,
        )
        trace.append(f"✔ Ingest ok: rows_clean={manifest.get('rows_clean')} first={manifest.get('first')} last={manifest.get('last')}")
    except Exception as e:
        # Wenn Clean nun immer noch fehlt → harter Fehler
        if not clean_path.exists():
            raise RuntimeError(f"Ingest fehlgeschlagen ({e}); keine Clean-CSV vorhanden.")
        trace.append(f"⚠ Ingest-Fehler, nutze vorhandene Datei: {e}")

    if not clean_path.exists():
        raise RuntimeError(f"Clean CSV fehlt weiterhin: {clean_path}")
    return clean_path

def _read_closes(clean_csv: Path) -> Tuple[List[str], List[float]]:
    rows = read_csv_rows(clean_csv)
    if not rows:
        raise RuntimeError(f"keine Daten in {clean_csv}")
    dts = [r[0] for r in rows]
    closes = [float(r[4]) for r in rows]
    return dts, closes

# ---------- Logik: SMA Cross ----------
def _signal_sma_cross(closes: List[float], fast: int, slow: int) -> Dict[str, object]:
    sf = _sma(closes, fast); ss = _sma(closes, slow)
    n = len(closes)
    if n < max(fast, slow) + 2:
        return {"signal": "NO_DATA", "reason": "zu wenig Bars"}
    i, prev = n - 1, n - 2
    f_now, s_now = sf[i], ss[i]
    f_prev, s_prev = sf[prev], ss[prev]
    px = closes[i]

    if None in (f_now, s_now, f_prev, s_prev):
        return {"signal": "NO_DATA", "reason": "SMA None"}

    cross_up   = f_prev <= s_prev and f_now > s_now
    cross_down = f_prev >= s_prev and f_now < s_now
    dist = abs(f_now - s_now) / px if px else 0.0
    slope = (f_now - f_prev) / px if px else 0.0

    if cross_up:
        conf = min(0.99, 0.5 + 3.0 * max(0.0, dist) + 2.0 * max(0.0, slope))
        return {"signal": "BUY", "confidence": round(conf, 3),
                "reason": f"Cross-UP (fast {f_now:.4f} > slow {s_now:.4f})",
                "fast": f_now, "slow": s_now, "price": px}
    if cross_down:
        conf = min(0.99, 0.5 + 3.0 * max(0.0, dist) + 2.0 * max(0.0, -slope))
        return {"signal": "SELL", "confidence": round(conf, 3),
                "reason": f"Cross-DOWN (fast {f_now:.4f} < slow {s_now:.4f})",
                "fast": f_now, "slow": s_now, "price": px}

    trend_up = f_now > s_now
    conf = 0.50 + min(0.40, 2.0 * max(0.0, dist))
    sig = "HOLD_UP" if trend_up else "HOLD_DOWN"
    return {"signal": sig, "confidence": round(conf, 3),
            "reason": f"Kein Cross; fast {f_now:.4f} vs slow {s_now:.4f}",
            "fast": f_now, "slow": s_now, "price": px}

# ---------- Preset laden ----------
def load_preset(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))

# ---------- Hauptfunktion ----------
def generate(preset: dict, symbols: List[str]) -> str:
    out_cfg = preset.get("output", {}) or {}
    out_dir = Path(out_cfg.get("dir", "reports/reco"))
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    run = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    day_dir = out_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = day_dir / f"reco_{run}.jsonl"
    json_path  = day_dir / f"reco_{run}.json"
    txt_path   = day_dir / f"reco_{run}.txt"

    logic = (preset.get("logic") or "sma_cross").lower()
    fast = int(preset.get("indicators", {}).get("sma_fast", 10))
    slow = int(preset.get("indicators", {}).get("sma_slow", 20))
    min_conf = float(preset.get("risk", {}).get("min_conf", 0.5))

    header = f"Signale • Preset={preset.get('name','?')}  {preset.get('asset')}/{preset.get('barsize')}  @ {_now_utc_iso()}"
    _print(header)

    results: List[dict] = []
    lines_txt: List[str] = [header]

    for sym_raw in symbols:
        sym = sym_raw.strip().upper()
        if not sym:
            continue

        trace: List[str] = [f"— {sym} —"]
        rec = {
            "ts": _now_utc_iso(),
            "preset": preset.get("name", "unnamed"),
            "asset": preset.get("asset", "stock"),
            "symbol": sym,
            "barsize": preset.get("barsize"),
            "duration": preset.get("duration"),
            "logic": logic,
            "workflow": trace
        }

        try:
            # Daten sicherstellen
            clean_csv = _ensure_clean_csv(sym, preset, trace)
            trace.append(f"✔ Clean bereit: {clean_csv.name}")

            # Preise lesen
            dts, closes = _read_closes(clean_csv)
            trace.append(f"✔ Gelesen: {len(closes)} Bars (Range: {dts[0]} → {dts[-1]})")

            # Signal berechnen
            if logic == "sma_cross":
                sig = _signal_sma_cross(closes, fast, slow)
            else:
                sig = {"signal": "UNSUPPORTED", "reason": f"logic={logic}"}
            rec.update(sig)

            # Deutung & Actionability
            rec["ok"] = sig.get("signal") not in ("NO_DATA", "UNSUPPORTED")
            rec["actionable"] = rec["ok"] and (float(sig.get("confidence", 0.0)) >= min_conf)
            rec["explain"] = _interpret(rec.get("signal", "NO_DATA"), float(sig.get("confidence", 0.0)), sig.get("reason", "-"))

            # Workflow-Erzählung
            if rec["ok"]:
                trace.append(f"✔ {rec['symbol']} → {rec['signal']}  conf={sig.get('confidence', 0.0):.2f}  px={sig.get('price','-')}")
                if not rec["actionable"]:
                    trace.append(f"ℹ unter min_conf ({min_conf:.2f}) → nur Hinweis")
            else:
                trace.append(f"⚠ Kein verwertbares Signal: {sig.get('reason','-')}")

            # Kurz-Zeile für TXT
            if rec["ok"]:
                lines_txt.append(f"  {sym:<8} {rec['signal']:<10} conf={sig.get('confidence',0.0):.2f}  px={sig.get('price','-')}")
                if not rec["actionable"]:
                    lines_txt.append("            (unter min_conf)")
            else:
                lines_txt.append(f"  {sym:<8} ERROR: {sig.get('reason','unknown')}")

            # Konsole: kompakter Ablauf
            _print("\n".join(trace))
        except Exception as e:
            rec["ok"] = False
            rec["error"] = str(e)
            trace.append(f"❌ Fehler: {e}")
            lines_txt.append(f"  {sym:<8} ERROR: {e}")
            _print("\n".join(trace))

        results.append(rec)

    # Dateien schreiben
    if out_cfg.get("write_jsonl", True):
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    if out_cfg.get("write_json", True):
        json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    if out_cfg.get("write_txt", True):
        txt_path.write_text("\n".join(lines_txt) + "\n", encoding="utf-8")

    _print(f"\n✅ Signale erstellt: {json_path}")
    return str(json_path)

# Optionaler CLI-Einstieg (falls direkt gestartet)
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Signal-Engine (SMA-Cross) mit Workflow-Ausgabe")
    ap.add_argument("--preset", default="presets/reco/default_stock_5m.json")
    ap.add_argument("--symbols", default="AAPL,MSFT,SPY")
    args = ap.parse_args()

    preset = load_preset(args.preset)
    syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    generate(preset, syms)

if __name__ == "__main__":
    main()


