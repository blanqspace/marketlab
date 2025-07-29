import os
import ast
import json
from datetime import datetime
import subprocess

# 📁 Absoluter Pfad zur Datei, fix in my_tools/summaries
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
summary_dir = os.path.join(SCRIPT_DIR, "summaries")
os.makedirs(summary_dir, exist_ok=True)

# 🕒 Dateiname mit Datum & Uhrzeit
from datetime import datetime
now = datetime.now().strftime("%Y-%m-%d_%H-%M")
summary_filename = f"summarize_project_{now}.md"
SUMMARY_PATH = os.path.join(summary_dir, summary_filename)

# 📂 Basis fürs Scannen bleibt das Hauptprojekt (eine Ebene höher)
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 🔍 Scan-Ergebnis
summary = []

# 🔒 Ausgeschlossene Pfade
EXCLUDED = ['.env', '__pycache__']

def is_valid_file(filename):
    return filename.endswith(('.py', '.json')) and not any(x in filename for x in EXCLUDED)

def summarize_python_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        globals_ = [n.targets[0].id for n in ast.walk(tree)
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)]
        imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
        return functions, classes, globals_, imports
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        return [], [], [], []

def summarize_json_keys(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.keys())
        return []
    except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError):
        return []

def scan_project():
    for root, _, files in os.walk(PROJECT_ROOT):
        if any(ex in root for ex in EXCLUDED):
            continue
        for file in files:
            if not is_valid_file(file):
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, PROJECT_ROOT)
            summary.append(f"\n### {rel_path}")

            if file.endswith('.py'):
                funcs, classes, globals_, imports = summarize_python_file(full_path)
                if imports:
                    summary.append(f"- 📦 Imports: {', '.join(sorted(set(imports)))}")
                if classes:
                    summary.append(f"- 🧩 Klassen: {', '.join(classes)}")
                if funcs:
                    summary.append(f"- ⚙️ Funktionen: {', '.join(funcs)}")
                if globals_:
                    summary.append(f"- 🧠 Globale Variablen: {', '.join(globals_)}")

            elif file.endswith('.json'):
                keys = summarize_json_keys(full_path)
                if keys:
                    summary.append(f"- 🔑 JSON-Schlüssel: {', '.join(keys)}")

if __name__ == "__main__":
    summary.append("# 🔍 Projektüberblick")
    summary.append(f"📁 Basisverzeichnis: `{PROJECT_ROOT}`\n")
    scan_project()

    with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(summary))

    print(f"\n✅ Übersicht wurde gespeichert unter:\n{SUMMARY_PATH}")
