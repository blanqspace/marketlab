#!/usr/bin/env python3
# bundle_picker.py
# Eingabe: kommaseparierte Pfade (Dateien/Ordner)
# Ausgabe: Markdown mit Dateiköpfen, Kennzahlen und CODE-INHALT

import os, sys, json, argparse

ALLOWED_EXTS = {".py", ".json", ".yaml", ".yml", ".md"}
EXCLUDE_FILES = {".DS_Store"}
EXCLUDE_DIRS = {".git", "__pycache__", ".vscode", ".idea"}
OUTPUT_DEFAULT = "code_bundle.md"

# Optionale Kurzbeschreibungen
PURPOSE = {
    "modules/bot/automation.py": "Bot-Orchestrierung: run_once, Loop ON/OFF, State & Summary.",
    "modules/bot/ask_flow.py": "ASK-Flow: Inline-Buttons/Timeout, Freigaben, idempotentes Dismiss.",
    "control/control_center.py": "Control/Event-Bus: RUN_ONCE, LOOP_ON/OFF, SAFE, STATUS.",
}

SENSITIVE_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TG_CHAT_CONTROL", "TG_CHAT_LOGS", "TG_CHAT_ORDERS", "TG_CHAT_ALERTS",
    "TG_ALLOWLIST", "TG_ALLOW_USER_IDS",
    "IB_HOST", "IB_PORT", "IB_CLIENT_ID",
}

def is_allowed_file(path: str) -> bool:
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in ALLOWED_EXTS and os.path.basename(path) not in EXCLUDE_FILES

def lang_of(ext: str) -> str:
    return {
        ".py": "python",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "md",
    }.get(ext.lower(), "")

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="strict") as f:
        return f.read()

def pretty_or_raw_json(text: str) -> str:
    try:
        obj = json.loads(text)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return text  # invalide JSON unverändert

def redact_env(text: str) -> str:
    # Einfache Redaktion: KEY=... → KEY=*** für definierte Schlüssel
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in SENSITIVE_KEYS:
                lines[i] = f"{key}=***"
    return "\n".join(lines)

def count_metrics(text: str, ext: str):
    lines = text.splitlines()
    total = len(lines)
    comments = sum(1 for l in lines if ext == ".py" and l.lstrip().startswith("#"))
    functions = sum(1 for l in lines if ext == ".py" and l.lstrip().startswith("def "))
    return total, comments, functions

def collect_paths(root: str, target: str) -> list[str]:
    out = []
    path = os.path.join(root, target)
    if os.path.isfile(path):
        if is_allowed_file(path):
            out.append(os.path.relpath(path, root))
    elif os.path.isdir(path):
        for r, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                full = os.path.join(r, f)
                if is_allowed_file(full):
                    out.append(os.path.relpath(full, root))
    else:
        print(f"❌ Nicht gefunden: {target}", file=sys.stderr)
    # stabile Reihenfolge
    out.sort()
    return out

def describe(relpath: str) -> str:
    p = relpath.replace("\\", "/")
    if p in PURPOSE:
        return PURPOSE[p]
    # heuristik
    if "/bot/" in p: return "Bot-Logik."
    if "/reco/" in p or "/signal/" in p: return "Signal-/Strategie-Logik."
    if "/trade/" in p: return "Trading/Order-Logik."
    if "/data/" in p: return "Daten-Pipeline."
    if "/telegram/" in p: return "Telegram-Interface."
    if "/shared/" in p: return "Shared-Core/Utils."
    if "/control/" in p: return "Control/Events."
    ext = os.path.splitext(p)[1].lower()
    if ext in {".yaml", ".yml"}: return "YAML-Konfiguration."
    if ext == ".json": return "JSON-Daten/Schema."
    if ext == ".md": return "Markdown."
    if ext == ".py": return "Python-Modul."
    return "Datei."

def main():
    ap = argparse.ArgumentParser(description="Bündelt Inhalte ausgewählter Dateien/Ordner in Markdown.")
    ap.add_argument("-i","--input", help='Kommaseparierte Pfade, z. B.: "modules/bot/automation.py, modules/bot/ask_flow.py, control/control_center.py"')
    ap.add_argument("-o","--output", default=OUTPUT_DEFAULT, help=f"Zieldatei (Markdown). Default: {OUTPUT_DEFAULT}")
    ap.add_argument("--no-redact", action="store_true", help="Keine Redaktion sensibler ENV-Zeilen.")
    args = ap.parse_args()

    if not args.input:
        s = input("Pfadliste eingeben: ").strip()
    else:
        s = args.input.strip()
    if not s:
        print("Keine Eingabe.", file=sys.stderr)
        sys.exit(1)

    root = os.getcwd()
    targets = [t.strip() for t in s.split(",") if t.strip()]
    relpaths = []
    seen = set()
    for t in targets:
        for p in collect_paths(root, t):
            if p not in seen:
                seen.add(p)
                relpaths.append(p)

    if not relpaths:
        print("Keine gültigen Dateien gefunden.", file=sys.stderr)
        sys.exit(2)

    lines = []
    lines.append("# 📦 Code-Bundle\n")

    for rel in relpaths:
        full = os.path.join(root, rel)
        ext = os.path.splitext(full)[1].lower()
        try:
            text = read_text(full)
        except UnicodeDecodeError:
            lines.append(f"\n## `{rel}`")
            lines.append("⚠️ Konnte Datei nicht lesen (Unicode-Fehler)\n")
            continue

        if ext == ".json":
            text = pretty_or_raw_json(text)
        if not args.no_redact and os.path.basename(rel) == ".env":
            text = redact_env(text)

        total, comments, functions = count_metrics(text, ext)
        purpose = describe(rel)
        lang = lang_of(ext)

        lines.append(f"\n## `{rel}`")
        meta = [f"Zeilen: {total}"]
        if ext == ".py":
            meta.append(f"Kommentare: {comments}")
            meta.append(f"Funktionen: {functions}")
        lines.append(f"- Zweck: {purpose}")
        lines.append(f"- " + ", ".join(meta) + "\n")
        lines.append(f"```{lang}")
        lines.append(text)
        lines.append("```")

    lines.append("\n---\n")
    lines.append("**Kopierzeile:**")
    lines.append("`" + ", ".join(relpaths) + "`")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ Gespeichert: {args.output}")
    print("Fertig.")

if __name__ == "__main__":
    main()
