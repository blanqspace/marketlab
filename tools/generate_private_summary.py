#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erstellt eine sichere Übersicht über .env und .gitignore, ohne Secrets preiszugeben.
Ausgabe: Markdown-Datei mit Key-Liste (maskiert) und ignorierten Dateien.

Beispiel:
  python tools/generate_private_summary.py --repo . --out reports/summary/private_summary.md
"""
from __future__ import annotations
import argparse, os, re, sys, fnmatch, json
from pathlib import Path
from datetime import datetime

RE_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

def read_env_file(p: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        m = RE_ENV_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        # entferne ggf. Quotes
        val = val.strip().strip("'").strip('"')
        env[key] = val
    return env

def classify_value(v: str) -> dict:
    d = {"empty": (v == ""), "len": len(v), "type": "string", "flags": []}
    lv = v.lower()
    # primitive Typen
    if lv in ("1","0","true","false","yes","no","on","off"):
        d["type"] = "bool-like"
    elif re.fullmatch(r"-?\d+", v or ""):
        d["type"] = "int-like"
    elif re.fullmatch(r"-?\d+\.\d+", v or ""):
        d["type"] = "float-like"
    # heuristics
    if len(v) >= 24:
        d["flags"].append("token-like")
    if ":" in v:
        d["flags"].append("has-colon")
    if v.count(",") >= 1:
        d["flags"].append("list-like")
    if v.startswith("sk-") or v.startswith("xoxb-"):
        d["flags"].append("secret-prefix")
    # maskierte Vorschau
    if not v:
        preview = ""
    elif len(v) <= 6:
        preview = "*" * len(v)
    else:
        preview = ("*" * (len(v) - 4)) + v[-4:]
    d["mask"] = preview
    return d

def load_all_envs(root: Path) -> list[tuple[Path, dict[str,str]]]:
    candidates = []
    for name in (".env",):
        p = root / name
        if p.exists():
            candidates.append(p)
    # zusätzlich .env.* außer beispiele
    for p in root.glob(".env.*"):
        if p.name.lower().endswith((".example", ".template", ".sample")):
            continue
        candidates.append(p)
    out = []
    for p in sorted(set(candidates)):
        out.append((p, read_env_file(p)))
    return out

def read_gitignore(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.exists():
        return []
    lines = []
    for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines

def match_gitignore(root: Path, patterns: list[str], max_list: int = 2000) -> list[Path]:
    """
    Sehr einfache fnmatch-basierte Umsetzung. Keine .gitignore-Prioritäten/!Negation.
    Ziel: Überblick, nicht 1:1-Git-Logik.
    """
    results: set[Path] = set()
    # sammle alle Dateien
    all_files = []
    for p in root.rglob("*"):
        if p.is_file():
            all_files.append(p)
        if len(all_files) > max_list:
            break
    # einfache Matches
    for pat in patterns:
        # Negationen (!) überspringen, um Verwirrung zu vermeiden
        if pat.startswith("!"):
            continue
        # Pfadbasierte und globale Pattern unterstützen
        for f in all_files:
            rel = str(f.relative_to(root)).replace("\\", "/")
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(f.name, pat):
                results.add(f)
    return sorted(results)

def human_size(n: int) -> str:
    for unit in ("B","KB","MB","GB","TB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def build_report(repo: Path, out: Path):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = []
    lines.append(f"# Private Summary – {repo.name}")
    lines.append("")
    lines.append(f"_Erzeugt am {ts}_")
    lines.append("")
    # ENV
    env_sets = load_all_envs(repo)
    if not env_sets:
        lines.append("## ENV")
        lines.append("- Keine .env-Datei gefunden.")
    else:
        lines.append("## ENV")
        for p, env in env_sets:
            lines.append(f"**Datei:** `{p.relative_to(repo)}`")
            if not env:
                lines.append("- (leer)")
                continue
            lines.append("")
            lines.append("| Key | Typ | Länge | Flags | Maske |")
            lines.append("|-----|-----|-------|-------|-------|")
            for k in sorted(env.keys()):
                info = classify_value(env[k])
                flags = ",".join(info["flags"]) if info["flags"] else ""
                lines.append(f"| `{k}` | {info['type']} | {info['len']} | {flags} | `{info['mask']}` |")
            lines.append("")
    # .gitignore
    patterns = read_gitignore(repo)
    lines.append("## .gitignore")
    if not patterns:
        lines.append("- Keine .gitignore gefunden oder keine Regeln.")
    else:
        lines.append("**Regeln:**")
        for pat in patterns:
            lines.append(f"- `{pat}`")
        # vorhandene ignorierte Dateien (vereinfachte Erkennung)
        matched = match_gitignore(repo, patterns)
        lines.append("")
        lines.append(f"**Gefundene ignorierte Dateien (vereinfachte Erkennung): {len(matched)}**")
        if matched:
            lines.append("")
            lines.append("| Datei | Größe |")
            lines.append("|-------|-------|")
            for f in matched[:200]:
                try:
                    sz = f.stat().st_size
                except OSError:
                    sz = 0
                lines.append(f"| `{f.relative_to(repo)}` | {human_size(sz)} |")
            if len(matched) > 200:
                lines.append(f"\n… weitere {len(matched) - 200} Dateien ausgelassen …")
    # Ausgabe schreiben
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Pfad zum Repo-Root")
    ap.add_argument("--out", default="reports/summary/private_summary.md", help="Zieldatei (Markdown)")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.out)
    if not repo.exists():
        print(f"Repo-Pfad nicht gefunden: {repo}", file=sys.stderr)
        sys.exit(2)

    p = build_report(repo, out)
    print(f"[OK] Summary geschrieben: {p}")

if __name__ == "__main__":
    main()
