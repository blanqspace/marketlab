import os
import json

EXCLUDE_FILES = ["__init__.py", ".env"]
EXCLUDE_DIRS = [".git", "__pycache__"]
ALLOWED_EXTS = {".py", ".json"}  # ← JSON zulassen
output_lines = ["# 🗂️ Projektdateien (gezielte Übersicht)\n"]

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def count_lines(lines, ext):
    total = len(lines)
    if ext == ".py":
        comments = sum(1 for l in lines if l.lstrip().startswith("#"))
    else:
        comments = 0  # JSON hat keine Kommentare im Standard
    return total, comments

def detect_code_fence(ext):
    return "python" if ext == ".py" else "json" if ext == ".json" else ""

def scan_file(path):
    rel_path = os.path.relpath(path, PROJECT_ROOT)
    if any(excl in rel_path for excl in EXCLUDE_FILES):
        return

    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
    except UnicodeDecodeError:
        output_lines.append(f"\n## `{rel_path}`")
        output_lines.append("⚠️ Konnte Datei nicht lesen (Unicode-Fehler)\n")
        return

    # Für JSON optional schön formatieren (failsafe bei invalider JSON)
    if ext == ".json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except Exception:
            # Falls keine valide JSON: Rohtext verwenden
            pass

    lines = text.splitlines()
    total, comments = count_lines(lines, ext)

    functions = 0
    if ext == ".py":
        functions = sum(1 for l in lines if l.lstrip().startswith("def "))

    fence = detect_code_fence(ext)

    output_lines.append(f"\n## `{rel_path}`")
    output_lines.append(f"- 📄 Zeilen: {total}, 🧾 Kommentare: {comments}, ⚙️ Funktionen: {functions}\n")
    output_lines.append(f"```{fence}")
    output_lines.extend(lines)
    output_lines.append("```")

def path_is_allowed_file(path):
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in ALLOWED_EXTS

def scan_target(rel_input):
    full_path = os.path.join(PROJECT_ROOT, rel_input)

    if path_is_allowed_file(full_path):
        scan_file(full_path)

    elif os.path.isdir(full_path):
        for root_dir, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in ALLOWED_EXTS and fname not in EXCLUDE_FILES:
                    scan_file(os.path.join(root_dir, fname))
    else:
        print(f"\n❌ Pfad ungültig oder nicht gefunden: `{rel_input}`\n")
        return False

    return True

def start():
    print("🔍 Engine3-Datei-Scanner\n")
    print("💡 Gib ein Verzeichnis oder eine Datei relativ zum Projekt ein (z. B. `modules/signal_scanner` oder `modules/signal_scanner/core.py`).")
    print("⬅️ Leere Eingabe = Abbruch")

    while True:
        user_input = input("\n📂 Pfad eingeben: ").strip()
        if not user_input:
            print("🚪 Vorgang abgebrochen.")
            return

        if scan_target(user_input):
            break  # nur wenn erfolgreich -> speichern

    # 🔧 Speicherort berechnen (allgemein über splitext)
    name_part, _ = os.path.splitext(os.path.basename(user_input))
    output_name = f"code_{name_part}.md"

    # 📁 Speicherziel: gleicher Ort wie Eingabe
    target_path = os.path.join(PROJECT_ROOT, user_input)
    target_dir = os.path.dirname(target_path) if os.path.isfile(target_path) else target_path
    output_file = os.path.join(target_dir, output_name)

    # 💾 Datei speichern
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Übersicht gespeichert unter:\n{output_file}")

if __name__ == "__main__":
    start()

