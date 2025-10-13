# Deprecated Components

This file tracks legacy modules and scripts that remain in the repository for compatibility but
are candidates for removal once downstream usage has migrated.

| Component | Status | Replacement / Notes |
|-----------|--------|---------------------|
| `marketlab.control_menu` | Deprecated | Use the Textual dashboard (`marketlab.tui.dashboard`) or CLI commands (`marketlab.cli`). Module now emits a `DeprecationWarning` on import. |
| Windows PowerShell launchers under `tools/*.ps1` | Pending removal | Linux/WSL workflow uses `tools/tmux_marketlab.sh` and `tools/stop_all.sh`. Remove once Windows support is re-evaluated. |
| `tools/tui_dashboard.py` | Legacy read-only view | Superseded by `marketlab.tui.dashboard`. Consider removing after verifying no downstream scripts import it. |

Please update this document when additional items are deprecated or removed.
