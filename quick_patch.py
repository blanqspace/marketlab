#!/usr/bin/env python3
# quick_patch.py
# Zweck: Die drei Änderungen zügig und idempotent in-place einspielen.
# Nutzung:
#   python quick_patch.py --dry-run
#   python quick_patch.py            (schreibt Dateien)
import re, sys, argparse, pathlib

ROOT = pathlib.Path(".")
TARGETS = {
    "automation": ROOT / "modules" / "bot" / "automation.py",
    "ask_flow": ROOT / "modules" / "bot" / "ask_flow.py",
    "control": ROOT / "control" / "control_center.py",
}

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")

def patch_automation(s: str) -> tuple[str, list[str]]:
    notes = []
    # 1) _safe_on() hinzufügen wenn fehlt
    if "_safe_on(" not in s:
        inject_after = r"def _load_state\([\s\S]*?return {}\n"
        m = re.search(inject_after, s)
        if m:
            add = """
def _safe_on() -> bool:
    p = Path("runtime/safe_mode.json")
    if not p.exists():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("safe", False))
    except Exception:
        return False
"""
            s = s[:m.end()] + add + s[m.end():]
            notes.append("automation: _safe_on() hinzugefügt")
    # 2) SAFE erzwingt OFF in run_once
    if "SAFE aktiv" not in s:
        s = re.sub(
            r"(order_type\s*=\s*\(exec_cfg\.get\(\s*\"order_type\"[\s\S]*?upper\(\)\))",
            r"\1\n    # SAFE → Exec deaktivieren\n    if _safe_on():\n        to_logs(\"SAFE aktiv → Exec wird nicht ausgeführt.\")\n        mode = \"OFF\"",
            s, count=1)
        notes.append("automation: SAFE->OFF in run_once")
    # 3) start_loop: Intervall ≥ ask_window+30
    if "ask_window + 30" not in s or "Überlappen" not in s:
        s = re.sub(
            r"itv\s*=\s*int\(interval_sec\s*or\s*cfg\.get\(\s*\"interval_sec\",\s*120\)\)\s*\)\s*",
            r"itv = int(interval_sec or cfg.get(\"interval_sec\", 120))",
            s, count=1)
        block = (
            "    try:\n"
            "        ask_window = int(cfg.get(\"telegram\", {}).get(\"ask_window_sec\", 120))\n"
            "        if itv < ask_window + 30:\n"
            "            to_logs(f\"Intervall {itv}s < ask_window+30 ({ask_window+30}s) → setze auf {ask_window+30}s.\")\n"
            "            itv = ask_window + 30\n"
            "    except Exception:\n"
            "        pass\n"
        )
        s = re.sub(r"(info\s*=\s*f\"⏱[^\n]*\n\s*print\(info\); to_control\(info\))",
                   block + r"\n\1", s, count=1)
        notes.append("automation: start_loop Intervall-Guard")
    # 4) _ensure_dirs: safe_mode.json default
    if "safe_mode.json" not in s:
        s = re.sub(
            r"(def _ensure_dirs\(\):\s*\n\s*for p in \[\"data\",[^\]]+\]\:\s*\n\s*Path\(p\)\.mkdir\(parents=True, exist_ok=True\)\s*)",
            r"\1\n    sm = Path(\"runtime\")/\"safe_mode.json\"\n    sm.parent.mkdir(parents=True, exist_ok=True)\n    if not sm.exists(): sm.write_text('{\"safe\": false}', encoding=\"utf-8\")\n",
            s, count=1)
        notes.append("automation: safe_mode.json default")
    return s, notes

def patch_ask_flow(s: str) -> tuple[str, list[str]]:
    notes = []
    # 1) _save_offset atomisch
    if ".tmp" not in s and "save_offset" in s:
        s = re.sub(
            r"def _save_offset\(ofs: int\) -> None:\s*\n\s*OFFSET_FILE\.parent[^\n]*\n\s*OFFSET_FILE\.write_text\(json\.dumps\(\{\"offset\": ofs\}\), encoding=\"utf-8\"\)",
            "def _save_offset(ofs: int) -> None:\n"
            "    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)\n"
            "    tmp = OFFSET_FILE.with_suffix('.tmp')\n"
            "    tmp.write_text(json.dumps({\"offset\": ofs}), encoding='utf-8')\n"
            "    tmp.replace(OFFSET_FILE)",
            s, count=1)
        notes.append("ask_flow: _save_offset atomisch")
    # 2) _rm_markup_with_retry: 400 not modified/not found → ok
    if "not modified" not in s.lower():
        s = re.sub(
            r"def _rm_markup_with_retry\(chat_id, message_id, text_done=\"Interaktion beendet.\", retries=3\) -> bool:[\s\S]*?except Exception:\s*\n\s*time\.sleep\(0\.8\)\s*\n\s*return False",
            "def _rm_markup_with_retry(chat_id, message_id, text_done=\"Interaktion beendet.\", retries=3) -> bool:\n"
            "    for _ in range(max(1, retries)):\n"
            "        try:\n"
            "            tg.edit_message_reply_markup(chat_id, message_id, None)\n"
            "            tg.edit_message_text(chat_id, message_id, text_done)\n"
            "            return True\n"
            "        except Exception as e:\n"
            "            se = str(e).lower()\n"
            "            if \"400\" in se and (\"not modified\" in se or \"not found\" in se):\n"
            "                return True\n"
            "            time.sleep(0.8)\n"
            "    return False",
            s, count=1)
        notes.append("ask_flow: idempotentes Dismiss")
    # 3) cancel_ask_flow räumt Buttons
    if "cancel_ask_flow" in s and "Abgebrochen" not in s:
        s = re.sub(
            r"def cancel_ask_flow\(\) -> None:\s*\n\s*CANCEL_FILE\.parent\.mkdir\(parents=True, exist_ok=True\)\s*\n\s*CANCEL_FILE\.write_text\(\"1\"\)",
            "def cancel_ask_flow() -> None:\n"
            "    CANCEL_FILE.parent.mkdir(parents=True, exist_ok=True)\n"
            "    CANCEL_FILE.write_text(\"1\")\n"
            "    st = _load_state()\n"
            "    try:\n"
            "        if st.get(\"chat_id\") and st.get(\"message_id\"):\n"
            "            _rm_markup_with_retry(st[\"chat_id\"], st[\"message_id\"], \"Abgebrochen.\")\n"
            "    except Exception:\n"
            "        pass",
            s, count=1)
        notes.append("ask_flow: cancel räumt Buttons")
    return s, notes

def patch_control(s: str) -> tuple[str, list[str]]:
    notes = []
    # 1) stop() join
    if "join(" not in s.split("def stop",1)[1]:
        s = re.sub(
            r"def stop\(self\):\s*\n\s*self\.running = False",
            "def stop(self):\n        self.running = False\n        try:\n            if self.worker and self.worker.is_alive():\n                self.worker.join(timeout=2.0)\n        except Exception:\n            pass",
            s, count=1)
        notes.append("control: stop() mit join")
    # 2) _read_interval max(itv, ask+30)
    if "ask_window_sec" not in s:
        s = re.sub(
            r"def _read_interval\(self\) -> int:[\s\S]*?return 120",
            "def _read_interval(self) -> int:\n"
            "        try:\n"
            "            import yaml\n"
            "            with open(\"config/bot.yaml\", \"r\", encoding=\"utf-8\") as f:\n"
            "                cfg = yaml.safe_load(f) or {}\n"
            "            itv = int(cfg.get(\"interval_sec\", 120))\n"
            "            askw = int((cfg.get(\"telegram\", {}) or {}).get(\"ask_window_sec\", 120))\n"
            "            return max(itv, askw + 30)\n"
            "        except Exception:\n"
            "            return 120",
            s, count=1)
        notes.append("control: Intervall-Guard")
    # 3) status() next_loop_eta_s
    if "next_loop_eta_s" not in s:
        s = re.sub(
            r"def status\(self\) -> Dict\[str, Any\]:[\s\S]*?return \{[\s\S]*?\}\n",
            "def status(self) -> Dict[str, Any]:\n"
            "        hb = _read_json(HB_FILE, {})\n"
            "        return {\n"
            "            \"safe\": self._safe_on(),\n"
            "            \"loop_on\": self.loop_on,\n"
            "            \"last_hb\": hb.get(\"ts\"),\n"
            "            \"queue_size\": self.q.qsize(),\n"
            "            \"interval_sec\": self.loop_interval,\n"
            "            \"next_loop_eta_s\": max(0, int(self._next_loop_ts - time.time())) if self.loop_on else None,\n"
            "        }\n",
            s, count=1)
        notes.append("control: status erweitert")
    return s, notes

def run(dry: bool):
    total_notes = []
    for key, path in TARGETS.items():
        if not path.exists():
            print(f"⚠️  fehlt: {path}")
            continue
        s0 = read(path)
        if key == "automation":
            s1, notes = patch_automation(s0)
        elif key == "ask_flow":
            s1, notes = patch_ask_flow(s0)
        else:
            s1, notes = patch_control(s0)
        if s1 != s0:
            total_notes.extend(notes)
            if dry:
                print(f"— würde patchen: {path}  [{', '.join(notes)}]")
            else:
                write(path, s1)
                print(f"✓ gepatcht: {path}  [{', '.join(notes)}]")
        else:
            print(f"= unverändert: {path}")
    if not total_notes:
        print("Keine Änderungen notwendig.")
    else:
        print("Änderungen:", *total_notes, sep="\n - ")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry=args.dry_run)
