import subprocess, sys, os, pathlib

def test_cli_help():
    out = subprocess.run([sys.executable, "-m", "marketlab", "--help"], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0
    # generische Hilfe-Prüfung
    assert "Usage" in out.stdout
    assert "control" in out.stdout

def test_backtest_with_dummy_data(tmp_path):
    # Dummy-Daten anlegen
    data_dir = pathlib.Path("data"); data_dir.mkdir(parents=True, exist_ok=True)
    csv = data_dir / "AAPL_15M.csv"
    csv.write_text("time,open,high,low,close,volume\n2024-01-01T00:00:00Z,1,1,1,1,100\n", encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "marketlab", "backtest", "--profile","default","--symbols","AAPL","--timeframe","15m"], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0
    assert "total" in out.stdout

