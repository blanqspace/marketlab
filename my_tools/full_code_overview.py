import os
from datetime import datetime

EXCLUDE_FILES = ["__init__.py", ".env"]
EXCLUDE_DIRS = [".git", "__pycache__"]
output_lines = ["# 🗂️ Vollständiger Projektinhalt (Codeübersicht)\n"]

def count_lines(lines):
    total = len(lines)
    comments = len([l for l in lines if l.strip().startswith("#")])
    return total, comments

def scan_file(path):
    rel_path = os.path.relpath(path, os.getcwd())
    if any(excl in rel_path for excl in EXCLUDE_FILES):
        return

    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    total, comments = count_lines(lines)
    functions = len([l for l in lines if l.strip().startswith("def ")])
    
    output_lines.append(f"\n## `{rel_path}`")
    output_lines.append(f"- 📄 Zeilen: {total}, 🧾 Kommentare: {comments}, ⚙️ Funktionen: {functions}\n")
    output_lines.append("```python")
    output_lines.extend([l.rstrip("\n") for l in lines])
    output_lines.append("```")

def scan_project(root="."):
    print("📢 Scanne alle Python-Dateien mit vollständigem Inhalt...")
    for root_dir, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py") and file not in EXCLUDE_FILES:
                full_path = os.path.join(root_dir, file)
                scan_file(full_path)

if __name__ == "__main__":
    # 📁 Zielordner: my_tools/summaries
    script_dir = os.path.dirname(os.path.abspath(__file__))
    summary_dir = os.path.join(script_dir, "summaries")
    os.makedirs(summary_dir, exist_ok=True)

    # 📅 Dateiname mit Datum & Uhrzeit
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    summary_filename = f"full_code_overview_{now}.md"
    output_path = os.path.join(summary_dir, summary_filename)

    # 🔍 Scan starten und Datei speichern
    scan_project(".")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Übersicht gespeichert in:\n{output_path}")

