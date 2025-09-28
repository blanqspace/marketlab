from pathlib import Path
import json, subprocess, sys, time
PY = sys.executable

def run_sma_batch(manifest_path="data_clean/manifest.json", params=None, out_dir=None):
    params = params or {}
    man = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    files = [e for e in man.get("files", []) if e.get("rows",0)>0]
    ts = time.strftime("%Y%m%d_%H%M%S")
    batch_dir = Path(out_dir or f"reports/runs/{ts}")
    batch_dir.mkdir(parents=True, exist_ok=True)
    results=[]
    for e in files:
        csv = e["clean"]
        args = [PY, "modules/backtest/sma.py", csv,
                "--fast", str(params.get("fast",10)),
                "--slow", str(params.get("slow",20)),
                "--exec", params.get("exec","close"),
                "--cash", str(params.get("cash",100000))]
        subprocess.run(args, check=False)
        results.append({"csv": csv, "params": params})
    (batch_dir/"batch.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Batch gespeichert: {batch_dir}")
    return str(batch_dir)

