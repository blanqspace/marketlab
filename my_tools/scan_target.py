import os

EXCLUDE_FILES = ["__init__.py", ".env"]
EXCLUDE_DIRS = [".git", "__pycache__"]
output_lines = ["# 🗂️ Projektdateien (gezielte Übersicht)\n"]

# Projektverzeichnis (wo das Skript liegt)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def count_lines(lines):
    total = len(lines)
    comments = len([l for l in lines if l.strip().startswith("#")])
    return total, comments

def scan_file(path):
    rel_path = os.path.relpath(path, PROJECT_ROOT)
    if any(excl in rel_path for excl in EXCLUDE_FILES):
        return

    try:
        with open(path, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except UnicodeDecodeError:
        output_lines.append(f"\n## `{rel_path}`")
        output_lines.append("⚠️ Konnte Datei nicht lesen (Unicode-Fehler)\n")
        return

    total, comments = count_lines(lines)
    functions = len([l for l in lines if l.strip().startswith("def ")])
    
    output_lines.append(f"\n## `{rel_path}`")
    output_lines.append(f"- 📄 Zeilen: {total}, 🧾 Kommentare: {comments}, ⚙️ Funktionen: {functions}\n")
    output_lines.append("```python")
    output_lines.extend([l.rstrip('\n') for l in lines])
    output_lines.append("```")

def scan_target(rel_input):
    full_path = os.path.join(PROJECT_ROOT, rel_input)

    if os.path.isfile(full_path) and full_path.endswith(".py"):
        scan_file(full_path)

    elif os.path.isdir(full_path):
        for root_dir, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if file.endswith(".py") and file not in EXCLUDE_FILES:
                    file_path = os.path.join(root_dir, file)
                    scan_file(file_path)
    else:
        print(f"\n❌ Pfad ungültig oder nicht gefunden: `{rel_input}`\n")
        return False

    return True

def start():
    print("🔍 Engine3-Datei-Scanner\n")
    print("💡 Gib ein Verzeichnis oder eine Datei relativ zum Projekt ein (z. B. `modules/signal_scanner` oder `modules/signal_scanner/core.py`).")
    print("⬅️ Leere Eingabe = Abbruch")

    while True:
        user_input = input("\n📂 Pfad eingeben: ").strip()

        if not user_input:
            print("🚪 Vorgang abgebrochen.")
            return

        success = scan_target(user_input)
        if success:
            break  # nur wenn erfolgreich -> speichern

    # 🔧 Speicherort berechnen
    name_part = os.path.basename(user_input).replace(".py", "")
    output_name = f"code_{name_part}.md"

    # 📁 Speicherziel: gleicher Ort wie Eingabe
    target_path = os.path.join(PROJECT_ROOT, user_input)
    if os.path.isfile(target_path):
        target_dir = os.path.dirname(target_path)
    else:
        target_dir = target_path

    output_file = os.path.join(target_dir, output_name)

    # 💾 Datei speichern
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Übersicht gespeichert unter:\n{output_file}")

if __name__ == "__main__":
    start()
