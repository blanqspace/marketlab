import os
from datetime import datetime

# 🔧 Pfade
DEV_LAB_ROOT = r"C:\Users\shaba\OneDrive\Anlagen\dev_lab\\"
INTEGRATION_LOG_PATH = r"C:\Users\shaba\OneDrive\Anlagen\engine3\integration_log.md"

# 📦 Kategorien für Feature-Typen
CATEGORIES = {
    "1": "Strategie",
    "2": "Datenquelle / Datenmanager",
    "3": "UI-Komponente / Menü",
    "4": "Visualisierung / Anzeige",
    "5": "Tool / Utility",
    "6": "Konfiguration / Struktur",
    "7": "Tests / Testumgebung",
}

# 📁 Vorlage für neue Feature-Ordner
TEMPLATE_FILES = {
    "main.py": '''\
# main.py
# Einstiegspunkt für dein Feature

from core import run_feature

if __name__ == "__main__":
    run_feature()
''',
    "core.py": '''\
# core.py
# Hier kommt deine Hauptlogik hin

def run_feature():
    print("🔧 Feature läuft... (hier deine Logik einfügen)")
''',
    "test_runner.py": '''\
# test_runner.py
# Testlogik für dein Feature

def run_tests():
    print("🧪 Tests ausführen...")
    # Beispiel-Testcode hier

if __name__ == "__main__":
    run_tests()
''',
    "notes.md": '''\
# 🧠 Feature-Dokumentation

## Ziel:
Beschreibe hier kurz, was dieses Feature tun soll.

## Status:
- [ ] Prototyp läuft
- [ ] getestet mit echten Daten
- [ ] bereit zur Integration

## Geplante Integration:
→ Modul: z. B. signal_scanner/tools
→ Zieldatei: z. B. symbol_selector.py
'''
}

def create_feature_folder(name, category):
    base_path = os.path.join(DEV_LAB_ROOT, name)
    os.makedirs(base_path, exist_ok=True)
    os.makedirs(os.path.join(base_path, "data"), exist_ok=True)

    print(f"\n📁 Erstelle Feature-Ordner: {base_path}")

    for filename, content in TEMPLATE_FILES.items():
        path = os.path.join(base_path, filename)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ {filename} erstellt.")
        else:
            print(f"⚠️ {filename} existiert bereits – übersprungen.")

    append_integration_log_entry(name, category)
    print(f"\n📂 '{name}' ({category}) ist bereit in dev_lab.")

def append_integration_log_entry(name, category):
    now_str = datetime.now().strftime("%Y-%m-%d")
    entry = f"""\n
---

## 🧩 {name}
**Kategorie**: {category}  
**Erstellt am**: {now_str}  
**Quelle**: dev_lab/{name}/  
**Geplante Integration**: [Bitte ausfüllen]  
**Status**: 🟡 in Entwicklung
"""

    os.makedirs(os.path.dirname(INTEGRATION_LOG_PATH), exist_ok=True)

    if not os.path.exists(INTEGRATION_LOG_PATH):
        with open(INTEGRATION_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("# 🔄 Integration Log – engine3\n")

    with open(INTEGRATION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)

    print("📝 Integrationseintrag ergänzt (integration_log.md).")

if __name__ == "__main__":
    print("🆕 Neues Modul/Komponente anlegen in dev_lab/")

    feature_name = input("🔤 Name eingeben (z. B. breakout_filter): ").strip()
    if not feature_name:
        print("❌ Kein Name eingegeben. Vorgang abgebrochen.")
        exit()

    print("\n📂 Wähle Kategorie:")
    for key, label in CATEGORIES.items():
        print(f"{key}. {label}")

    category_choice = input("\n🗂️ Nummer der Kategorie eingeben: ").strip()
    category = CATEGORIES.get(category_choice)

    if not category:
        print("❌ Ungültige Auswahl. Vorgang abgebrochen.")
    else:
        create_feature_folder(feature_name, category)

