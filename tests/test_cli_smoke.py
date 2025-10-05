import subprocess, sys, os

def test_cli_help():
    out = subprocess.run([sys.executable, "-m", "marketlab", "--help"], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0
    assert "MarketLab CLI" in out.stdout

def test_backtest_runs_empty():
    out = subprocess.run([sys.executable, "-m", "marketlab", "backtest", "--profile","default","--symbols","AAPL","--timeframe","15m"], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0
    assert "backtest.start" in out.stdout